from .utils import utc_now_aware, pack_to_bytes, unpack_from_bytes, get_packer, get_unpacker


def test_pack_unpack():
    data = [
        b'bytes',
        'string',
        utc_now_aware(),
    ]

    packed = pack_to_bytes(data)
    assert isinstance(packed, bytes)
    unpacked = unpack_from_bytes(packed)
    assert unpacked == data


def test_packer_unpacker():
    data = [
        b'bytes',
        'string',
        utc_now_aware(),
    ]

    packer = get_packer()
    unpacker = get_unpacker()

    packed = packer.pack(data)
    assert isinstance(packed, bytes)
    unpacker.feed(packed)
    unpacked = next(unpacker)
    assert unpacked == data
