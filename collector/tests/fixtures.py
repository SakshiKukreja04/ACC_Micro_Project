"""Sample RSS and Atom XML fixtures for collector tests."""

VALID_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/">
  <channel>
    <title>Tech Insights Feed</title>
    <link>https://example.com</link>
    <description>Sample tech news feed</description>
    <item>
      <title><![CDATA[New Quantum Computing Breakthrough Announced]]></title>
      <link>https://example.com/articles/quantum-breakthrough?utm_source=rss&amp;utm_medium=feed&amp;ref=news</link>
      <guid>https://example.com/articles/quantum-breakthrough</guid>
      <pubDate>Thu, 24 Oct 2026 10:00:00 GMT</pubDate>
      <description><![CDATA[<p>Researchers have achieved a <strong>major milestone</strong> in fault-tolerant qubits.</p>]]></description>
      <content:encoded><![CDATA[<p>Full article text explaining the new topological qubit architecture in detail.</p>]]></content:encoded>
      <category>Quantum</category>
    </item>
    <item>
      <title>Autonomous Systems Pass Road Safety Validation</title>
      <link>https://example.com/articles/autonomous-safety/?utm_campaign=daily</link>
      <guid>https://example.com/articles/autonomous-safety</guid>
      <pubDate>Thu, 24 Oct 2026 12:30:00 +0000</pubDate>
      <description>Regulatory bodies approve new level-4 urban driving protocols.</description>
      <category>AI &amp; Robotics</category>
    </item>
  </channel>
</rss>
"""

MALFORMED_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Broken Feed</title>
    <item>
      <title>Unclosed Tag Example
      <link>https://example.com/broken
      <description>Missing closing tags everywhere...
"""

MISSING_FIELDS_RSS_XML = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>Incomplete Feed</title>
    <item>
      <!-- Missing title -->
      <link>https://example.com/missing-title</link>
      <description>An entry without title</description>
    </item>
    <item>
      <title>Entry Without Link</title>
      <!-- Missing link -->
      <description>An entry without URL</description>
    </item>
    <item>
      <title>Entry with Missing PubDate</title>
      <link>https://example.com/missing-date</link>
      <description>Valid except date is missing</description>
    </item>
  </channel>
</rss>
"""
