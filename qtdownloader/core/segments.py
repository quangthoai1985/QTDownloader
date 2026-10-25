"""Chia đoạn động (dynamic segmentation).

Ý tưởng (theo mô tả công khai của IDM, tự cài đặt lại):
  * File bắt đầu là 1 đoạn. Mỗi kết nối mới lấy NỬA SAU của đoạn còn lại lớn nhất.
  * Kết nối tải xong phần mình KHÔNG đóng: nó lại lấy nửa sau của đoạn lớn nhất
    đang tải dở → không mất thời gian bắt tay TCP/TLS (tái dùng keep-alive).
  * Bổ sung của QT Downloader: mỗi kết nối gửi yêu cầu theo "cửa sổ" (Range có giới hạn).
    Khi chia đoạn, ưu tiên cắt sau cửa sổ đang bay của nạn nhân, để nạn nhân đọc hết
    phản hồi và giữ được kết nối thay vì phải huỷ giữa chừng.

Mọi thao tác trên SegmentMap chạy trong 1 luồng asyncio nên không cần khoá.
"""

from __future__ import annotations

from dataclasses import dataclass

ALIGN = 64 * 1024


@dataclass(eq=False)
class Segment:
    start: int
    end: int          # không bao gồm
    pos: int          # byte kế tiếp sẽ nhận (đã nhận vào bộ đệm)
    written: int      # byte đã ghi xuống tệp (<= pos)
    worker: int | None = None
    req_end: int = 0  # cuối cửa sổ yêu cầu đang bay (0 = không có)

    @property
    def remaining(self) -> int:
        return max(0, self.end - self.pos)

    @property
    def done(self) -> bool:
        return self.pos >= self.end


def _align_up(x: int) -> int:
    return (x + ALIGN - 1) // ALIGN * ALIGN


class SegmentMap:
    def __init__(self, size: int, segs: list[Segment] | None = None):
        self.size = size
        self.segs: list[Segment] = segs if segs is not None else [Segment(0, size, 0, 0)]

    # ---------- lưu / nạp ----------
    @classmethod
    def from_saved(cls, size: int, saved: list) -> "SegmentMap":
        segs: list[Segment] = []
        try:
            for start, end, pos in saved:
                start, end, pos = int(start), int(end), int(pos)
                if not (0 <= start <= pos <= end <= size):
                    raise ValueError
                segs.append(Segment(start, end, pos, pos))
        except (TypeError, ValueError):
            return cls(size)
        segs.sort(key=lambda s: s.start)
        # phải phủ kín [0, size) không chồng lấn, nếu không thì làm lại từ đầu
        cursor = 0
        for s in segs:
            if s.start != cursor:
                return cls(size)
            cursor = s.end
        if cursor != size or not segs:
            return cls(size)
        return cls(size, segs)

    def to_saved(self) -> list[list[int]]:
        """Lưu theo `written` (đã xuống đĩa).

        [a, b, b] (xong) + [b, c, p] gộp được thành [a, c, p] vì [a, p) đều đã có dữ liệu.
        """
        out: list[list[int]] = []
        for s in self.segs:
            if out and out[-1][2] == out[-1][1]:
                out[-1][1] = s.end
                out[-1][2] = s.written
            else:
                out.append([s.start, s.end, s.written])
        return out

    # ---------- thống kê ----------
    def received(self) -> int:
        return sum(s.pos - s.start for s in self.segs)

    def written(self) -> int:
        return sum(s.written - s.start for s in self.segs)

    def complete(self) -> bool:
        return all(s.written >= s.end for s in self.segs)

    def all_received(self) -> bool:
        return all(s.pos >= s.end for s in self.segs)

    # ---------- phân việc ----------
    def take_unowned(self) -> Segment | None:
        """Đoạn chưa ai nhận (sau khi resume) — chọn đoạn còn nhiều nhất."""
        free = [s for s in self.segs if s.worker is None and s.remaining > 0]
        if not free:
            return None
        return max(free, key=lambda s: s.remaining)

    def split_largest(self, min_split: int) -> Segment | None:
        """Cắt nửa sau của đoạn đang tải còn lại lớn nhất, trả về đoạn mới (chưa có worker)."""
        best: Segment | None = None
        for s in self.segs:
            if s.worker is None:
                continue
            if best is None or s.remaining > best.remaining:
                best = s
        if best is None or best.remaining < 2 * min_split:
            return None
        mid = _align_up(best.pos + best.remaining // 2)
        # Không cắt vào cửa sổ đang bay nếu phần sau cửa sổ vẫn đủ lớn → nạn nhân giữ được kết nối
        if best.req_end > mid and best.end - best.req_end >= min_split:
            mid = best.req_end
        if mid - best.pos < min_split or best.end - mid < min_split:
            return None
        new = Segment(mid, best.end, mid, mid)
        best.end = mid
        if best.req_end > mid:
            best.req_end = mid
        self.segs.insert(self.segs.index(best) + 1, new)
        return new

    def reset(self) -> None:
        self.segs = [Segment(0, self.size, 0, 0)]
