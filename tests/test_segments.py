from qtdownloader.core.segments import ALIGN, Segment, SegmentMap
from qtdownloader.core.util import expand_batch_pattern, sanitize_filename
from qtdownloader.core.probe import parse_content_disposition, parse_content_range

MB = 1024 * 1024


def covered(segmap):
    cur = 0
    for s in segmap.segs:
        assert s.start == cur
        assert s.start <= s.pos <= s.end
        cur = s.end
    assert cur == segmap.size


def test_split_takes_second_half_of_largest():
    m = SegmentMap(100 * MB)
    first = m.take_unowned()
    first.worker = 1
    new = m.split_largest(MB)
    assert new is not None and new.worker is None
    assert first.end == new.start
    assert abs(new.start - 50 * MB) <= ALIGN
    covered(m)
    new.worker = 2
    third = m.split_largest(MB)
    assert third.start > 0 and len(m.segs) == 3
    covered(m)


def test_split_respects_in_flight_window():
    m = SegmentMap(100 * MB)
    s = m.take_unowned()
    s.worker = 1
    s.pos = s.written = 10 * MB
    s.req_end = 70 * MB          # cửa sổ đang bay vượt quá điểm giữa (55 MB)
    new = m.split_largest(MB)
    assert new.start == 70 * MB  # cắt sau cửa sổ → kết nối cũ đọc trọn phản hồi
    assert s.end == 70 * MB


def test_no_split_when_too_small():
    m = SegmentMap(3 * MB)
    s = m.take_unowned()
    s.worker = 1
    s.pos = 2 * MB
    assert m.split_largest(MB) is None


def test_save_load_roundtrip_and_compaction():
    m = SegmentMap(10 * MB, [
        Segment(0, 2 * MB, 2 * MB, 2 * MB),
        Segment(2 * MB, 5 * MB, 3 * MB, 3 * MB),
        Segment(5 * MB, 10 * MB, 7 * MB, 6 * MB),   # pos > written: chỉ lưu phần đã ghi
    ])
    saved = m.to_saved()
    assert saved == [[0, 5 * MB, 3 * MB], [5 * MB, 10 * MB, 6 * MB]]
    m2 = SegmentMap.from_saved(10 * MB, saved)
    covered(m2)
    assert m2.written() == 3 * MB + MB
    assert m2.take_unowned().start == 5 * MB  # đoạn còn nhiều nhất trước


def test_from_saved_rejects_corrupt():
    m = SegmentMap.from_saved(10, [[0, 4, 2], [5, 10, 6]])  # hở 4..5
    assert len(m.segs) == 1 and m.segs[0].pos == 0


def test_helpers():
    assert expand_batch_pattern("http://x/f[01-03].zip") == [
        "http://x/f01.zip", "http://x/f02.zip", "http://x/f03.zip"]
    assert expand_batch_pattern("http://x/[a-c].jpg")[-1] == "http://x/c.jpg"
    assert sanitize_filename('a<b>:"c|?.txt') == "a_b___c__.txt"
    assert sanitize_filename("CON.txt") == "_CON.txt"
    assert parse_content_range("bytes 10-19/100") == (10, 19, 100)
    assert parse_content_range("bytes 0-0/*") == (0, 0, -1)
    assert parse_content_disposition("attachment; filename*=UTF-8''T%C3%A0i%20li%E1%BB%87u.pdf") == "Tài liệu.pdf"
    assert parse_content_disposition('attachment; filename="report v2.zip"') == "report v2.zip"
