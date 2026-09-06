from app.engine.deck import Shoe


def test_same_seed_produces_the_same_shuffle_order():
    a = Shoe(num_decks=1, seed=42)
    b = Shoe(num_decks=1, seed=42)

    assert [str(c) for c in a._cards] == [str(c) for c in b._cards]


def test_different_seeds_produce_different_shuffle_order():
    a = Shoe(num_decks=1, seed=1)
    b = Shoe(num_decks=1, seed=2)

    assert [str(c) for c in a._cards] != [str(c) for c in b._cards]


def test_shoe_size_scales_with_num_decks():
    shoe = Shoe(num_decks=6, seed=1)

    assert shoe.cards_remaining() == 6 * 52


def test_snapshot_and_restore_preserve_draw_order():
    original = Shoe(num_decks=2, seed=7)
    original.draw()
    original.draw()
    original.draw()

    restored = Shoe.restore(**original.snapshot())

    assert restored.cards_remaining() == original.cards_remaining()
    while original.cards_remaining():
        assert str(restored.draw()) == str(original.draw())


def test_restore_gets_a_fresh_rng_for_future_reshuffles():
    original = Shoe(num_decks=1, seed=99)
    restored = Shoe.restore(**original.snapshot())

    assert restored._rng is not original._rng
