class Borg:
    # thread unsafe
    def __new__(cls, *args):
        assert hasattr(cls, '_shared_state'), 'must has _shared_state'
        instance = super().__new__(cls, *args)
        instance.__dict__ = cls._shared_state
        return instance
