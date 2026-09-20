from messy_weather_nfl_bot.poster.console import ConsolePoster


def test_post_thread_empty_returns_no_refs() -> None:
    poster = ConsolePoster()
    assert poster.post_thread([]) == []


def test_post_thread_single_text_posts_once() -> None:
    poster = ConsolePoster()
    refs = poster.post_thread(["hello"])
    assert len(refs) == 1
    assert refs[0].root_id == refs[0].id
    assert poster.posted == ["hello"]


def test_post_thread_multiple_texts_chain_replies_to_same_root() -> None:
    poster = ConsolePoster()
    refs = poster.post_thread(["root", "reply 1", "reply 2"])

    assert len(refs) == 3
    assert poster.posted == ["root", "reply 1", "reply 2"]

    root_id = refs[0].id
    # Every post in the thread traces back to the same root, not just its immediate parent.
    assert all(ref.root_id == root_id for ref in refs)
    assert refs[0].id != refs[1].id != refs[2].id
