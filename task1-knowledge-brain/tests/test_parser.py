from app.parser import parse_article


def test_image_reference_changes_article_content_hash():
    first = parse_article(
        '<html><h1>Account settings</h1><main><p>Open the account screen.</p>'
        '<img src="/images/settings-a.png" alt="Account settings screenshot"></main></html>',
        "https://support.brilliantdirectories.com/help/account",
    )
    changed = parse_article(
        '<html><h1>Account settings</h1><main><p>Open the account screen.</p>'
        '<img src="/images/settings-b.png" alt="Account settings screenshot"></main></html>',
        "https://support.brilliantdirectories.com/help/account",
    )

    assert first.content_hash != changed.content_hash