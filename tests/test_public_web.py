from src.sources.public_web import PublicWebSource


def test_extracts_jsonld_and_tel_without_duplicates():
    html = """
    <html>
      <head>
        <title>Acme Export | Home</title>
        <script type="application/ld+json">
          {"@type":"Organization","name":"Acme Export","telephone":"+1 202 456 1111"}
        </script>
      </head>
      <body><a href="tel:+12024561111">Call</a></body>
    </html>
    """
    records = list(PublicWebSource._extract(html))
    assert ("Acme Export", "+1 202 456 1111") in records
    assert ("Acme Export", "+12024561111") in records


def test_extracts_organization_from_jsonld_graph():
    html = """
    <script type="application/ld+json">
      {"@graph":[
        {"@type":"WebSite","name":"Site"},
        {"@type":["Organization","Thing"],"name":"Global Parts","telephone":["+49 30 123456"]}
      ]}
    </script>
    """
    assert list(PublicWebSource._extract(html)) == [
        ("Global Parts", "+49 30 123456")
    ]


def test_extracts_labeled_phone_from_visible_text():
    html = """
    <html><head><title>KHD Humboldt Wedag | Contact</title></head>
    <body>Headquarters, Cologne, Germany Phone: +49 221 6504 0</body></html>
    """
    assert list(PublicWebSource._extract(html)) == [
        ("KHD Humboldt Wedag", "+49 221 6504 0")
    ]
