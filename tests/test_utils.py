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

    def test_moveitpassenger_url_uses_moveit_domain(self):
        articles = [
            {"id": 16613564222105, "uuid": "u1", "name": "Unsubscribe", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="moveitpassenger", language_locale="en-ph",
            knowledge_source_id="ks-123"
        )
        url = result[0]["url"]
        assert url == "https://help.moveit.com.ph/passenger/en-ph/16613564222105"

    def test_moveitpassenger_url_not_grab_domain(self):
        articles = [
            {"id": 123, "uuid": "u1", "name": "A", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="moveitpassenger", language_locale="en-ph",
            knowledge_source_id="ks-123"
        )
        assert "help.grab.com" not in result[0]["url"]
        assert "moveitpassenger" not in result[0]["url"]

    def test_moveitdriver_url_uses_grab_driver_path(self):
        articles = [
            {"id": 40001000, "uuid": "u1", "name": "Driver Article", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        result = app.convert_to_ada_format(
            articles, user_type="moveitdriver", language_locale="en-ph",
            knowledge_source_id="ks-123"
        )
        assert result[0]["url"] == "https://help.grab.com/driver/en-ph/40001000"

    def test_standard_user_type_url(self):
        articles = [
            {"id": 99, "uuid": "u1", "name": "A", "body": "B",
             "parentId": None, "caseL1": None, "caseL2": None, "caseL3": None, "position": 0}
        ]
        for user_type, locale in [("passenger", "en-my"), ("driver", "en-sg"), ("merchant", "en-ph")]:
            result = app.convert_to_ada_format(
                articles, user_type=user_type, language_locale=locale,
                knowledge_source_id="ks-123"
            )
            assert result[0]["url"] == f"https://help.grab.com/{user_type}/{locale}/99"


class TestFilterMoveitArticles:

    def test_filters_within_range(self):
        articles = [
            {"id": 40000747, "name": "First MoveIt"},
            {"id": 40001000, "name": "Mid MoveIt"},
            {"id": 40001434, "name": "Last MoveIt"},
        ]
        result = app.filter_moveit_articles(articles)
        assert len(result) == 3

    def test_excludes_outside_range(self):
        articles = [
            {"id": 40000746, "name": "Just below range"},
            {"id": 40001000, "name": "In range"},
            {"id": 40001435, "name": "Just above range"},
        ]
        result = app.filter_moveit_articles(articles)
        assert len(result) == 1
        assert result[0]["name"] == "In range"

    def test_boundary_start(self):
        articles = [{"id": 40000747, "name": "Start boundary"}]
        assert len(app.filter_moveit_articles(articles)) == 1

    def test_boundary_end(self):
        articles = [{"id": 40001434, "name": "End boundary"}]
        assert len(app.filter_moveit_articles(articles)) == 1

    def test_empty_input(self):
        assert app.filter_moveit_articles([]) == []

    def test_none_id_skipped(self):
        articles = [{"id": None, "name": "No ID"}, {"id": 40001000, "name": "Valid"}]
        result = app.filter_moveit_articles(articles)
        assert len(result) == 1
        assert result[0]["name"] == "Valid"
