# -*- coding:utf-8 -*-
from __future__ import division, print_function, absolute_import, unicode_literals

class Null:
    def __bool__(self):
        return False

    def __len__(self):
        return 0

    def __iter__(self):
        return iter([])

    def __getattr__(self, item):
        return self

    def __call__(self, *args, **kwargs):
        return self

    def __getitem__(self, key):
        return _null


_null = Null()


class Mapper:
    def __init__(self, iterable=()):
        self._items = list(iterable)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)

    def __bool__(self):
        return bool(self._items)

    def __getitem__(self, key):
        try:
            return self._items[key]
        except (KeyError, IndexError):
            return _null

    def __setitem__(self, key, value):
        self._items[key] = value
        return self[key]

    def __getattr__(self, item):
        return Mapper([getattr(x, item) for x in self])

    def __call__(self, *args, **kwargs):
        return Mapper([x(*args, **kwargs) for x in self])

    def __eq__(self, other):
        if len(other) != len(self):
            return False
        for x, y in zip(self, other):
            if x != y:
                return False
        return True

    def __str__(self):
        return str(self._items)


def test_mapper():
    l = ['a', 'b']
    m = Mapper(l)
    assert bool(m) is True
    assert len(m) == 2
    assert bool(Mapper()) is False
    assert len(Mapper()) == 0
    assert m[0] == 'a'
    assert m[1] == 'b'
    m[0] += 'a'
    assert m[0] == 'aa'
    m2 = m.upper()
    assert m[0] == 'aa'
    assert m[1] == 'b'
    assert m2[0] == 'AA'
    assert m2[1] == 'B'
    assert len(m2) == 2
    l = []
    for x in m:
        l.append(x)
    assert len(l) == 2
    assert l[0] == 'aa'
    assert l[1] == 'b'
    assert l == m
    assert ['aa', ''] != m
    assert ['aa'] != m