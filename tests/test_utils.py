"""
Tests for pure utility functions: clean_api_key, extract_articles,
filter_articles, convert_to_ada_format.
"""
import app


class TestCleanApiKey:

    def test_strips_whitespace(self):
        assert app.clean_api_key("  abc123  ") == "abc123"

    def test_removes_non_ascii(self):
        assert app.clean_api_key("abc\xff123") == "abc123"

    def test_empty_string(self):
        assert app.clean_api_key("") == ""

    def test_none_returns_empty(self):
        assert app.clean_api_key(None) == ""

    def test_valid_key_unchanged(self):
        key = "0667adf1bfd0477bf92a558e4b1dbbe1"
        assert app.clean_api_key(key) == key


class TestExtractArticles:

    def test_extracts_fields(self):
        data = {
            "articles": [
                {"id": 1, "uuid": "u1", "name": "Article 1", "body": "<p>Hello</p>",
                 "parentId": None, "caseL1": "Cat", "caseL2": None, "caseL3": None, "position": 0}
            ]
        }
        articles = app.extract_articles(data)
        assert len(articles) == 1
        assert articles[0]["name"] == "Article 1"
        assert articles[0]["id"] == 1

    def test_empty_data_returns_empty(self):
        assert app.extract_articles({}) == []
        assert app.extract_articles(None) == []

    def test_missing_articles_key(self):
        assert app.extract_articles({"other": []}) == []

    def test_html_converted_to_markdown(self):
        data = {
            "articles": [
                {"id": 1, "uuid": "u1", "name": "A", "body": "<b>Bold</b>",
                 "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
            ]
        }
        articles = app.extract_articles(data)
        assert "Bold" in articles[0]["body"]


class TestFilterArticles:

    def test_filters_empty_articles(self):
        articles = [
            {"id": 1, "name": "Good", "body": "Some real content here for testing purposes."},
            {"id": 2, "name": "Empty", "body": ""},
            {"id": 3, "name": "Whitespace only", "body": "   "},
        ]
        production, empty, _ = app.filter_articles(articles, filter_empty=True)
        assert len(production) == 1
        assert production[0]["name"] == "Good"

    def test_no_filter_returns_all(self):
        articles = [
            {"name": "Good", "body": "Content"},
            {"name": "Empty", "body": ""},
        ]
        production, empty, _ = app.filter_articles(articles, filter_empty=False)
        assert len(production) == 2

    def test_empty_input(self):
        result = app.filter_articles([], filter_empty=True)
        assert result == ([], [], [])


class TestConvertToAdaFormat:

    def test_output_has_required_fields(self):
        articles = [
            {"id": 42, "uuid": "u1", "name": "Test Article", "body": "Content",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="passenger", language_locale="en-my",
            knowledge_source_id="ks-123"
        )
        assert len(result) == 1
        article = result[0]
        # Ada format uses "content" (not "body"), language is the full locale string
        required_fields = ["id", "name", "content", "language", "url",
                           "knowledge_source_id", "external_updated"]
        for field in required_fields:
            assert field in article, f"Missing field: {field}"

    def test_language_set_from_locale(self):
        articles = [
            {"id": 1, "uuid": "u1", "name": "A", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="passenger", language_locale="en-my",
            knowledge_source_id="ks-123"
        )
        # language is the full locale string, not just the language code
        assert result[0]["language"] == "en-my"

    def test_override_language(self):
        articles = [
            {"id": 1, "uuid": "u1", "name": "A", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="passenger", language_locale="en-my",
            knowledge_source_id="ks-123", override_language="ms"
        )
        assert result[0]["language"] == "ms"

    def test_url_contains_user_type(self):
        articles = [
            {"id": 5, "uuid": "u1", "name": "Driver Article", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="driver", language_locale="en-sg",
            knowledge_source_id="ks-123"
        )
        assert "driver" in result[0]["url"].lower()

    def test_knowledge_source_id_set(self):
        articles = [
            {"id": 1, "uuid": "u1", "name": "A", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="passenger", language_locale="en-my",
            knowledge_source_id="ks-xyz"
        )
        assert result[0]["knowledge_source_id"] == "ks-xyz"
