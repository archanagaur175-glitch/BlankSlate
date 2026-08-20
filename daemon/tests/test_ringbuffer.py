import numpy as np
import pytest

from blankslate.audio.ringbuffer import RingBuffer


def test_append_and_get() -> None:
    buf = RingBuffer(100)
    buf.append(np.arange(50, dtype=np.float32))
    assert buf.filled == 50
    out = buf.get_all()
    np.testing.assert_array_equal(out, np.arange(50, dtype=np.float32))


def test_drops_oldest() -> None:
    buf = RingBuffer(100)
    buf.append(np.full(80, fill_value=1.0, dtype=np.float32))
    buf.append(np.full(80, fill_value=2.0, dtype=np.float32))
    assert buf.filled == 100
    out = buf.get_all()
    assert out.size == 100
    assert set(np.unique(out)) == {1.0, 2.0}


def test_get_last_window() -> None:
    buf = RingBuffer(1000)
    buf.append(np.arange(300, dtype=np.float32))
    tail = buf.get_last(50)
    np.testing.assert_array_equal(tail, np.arange(250, 300, dtype=np.float32))


def test_get_last_more_than_filled() -> None:
    buf = RingBuffer(100)
    buf.append(np.full(10, fill_value=7.0, dtype=np.float32))
    assert buf.get_last(500).size == 10


def test_get_last_zero() -> None:
    buf = RingBuffer(100)
    assert buf.get_last(0).size == 0
    assert buf.get_all().size == 0


def test_oversized_append() -> None:
    buf = RingBuffer(10)
    buf.append(np.arange(25, dtype=np.float32))
    assert buf.filled == 10
    np.testing.assert_array_equal(buf.get_all(), np.arange(15, 25, dtype=np.float32))


def test_invalid_capacity() -> None:
    with pytest.raises(ValueError):
        RingBuffer(0)


def test_reset() -> None:
    buf = RingBuffer(10)
    buf.append(np.ones(5))
    buf.reset()
    assert buf.filled == 0
    assert buf.get_all().size == 0
