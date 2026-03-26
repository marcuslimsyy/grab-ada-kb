import streamlit as st
import requests
import json
import pandas as pd
import uuid
import random
import string
import re
import os
from pathlib import Path
from bs4 import BeautifulSoup
import html2text
from datetime import datetime
import time
from collections import deque

# --- Rate limiting & retry constants ---
_rate_limiter = deque(maxlen=100)  # sliding window: timestamps of last 100 API calls
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds
MAX_RETRIES = 3
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 60.0  # seconds
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def enforce_rate_limit():
    """Block until we're within the 100 req/min rate limit (sliding window)."""
    now = time.time()
    if len(_rate_limiter) == RATE_LIMIT_REQUESTS:
        oldest = _rate_limiter[0]
        window_elapsed = now - oldest
        if window_elapsed < RATE_LIMIT_WINDOW:
            sleep_for = RATE_LIMIT_WINDOW - window_elapsed + 0.05  # small buffer
            time.sleep(sleep_for)
    _rate_limiter.append(time.time())


# Set page title
st.title("Grab Articles to Ada Knowledge Base Manager")

# Initialize API call log in session state
if 'api_call_log' not in st.session_state:
    st.session_state.api_call_log = []

def log_api_call(method, url, status_code, success, details="", response_data=None):
    """Log API call details"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_entry = {
        "timestamp": timestamp,
        "method": method,
        "url": url,
        "status_code": status_code,
        "success": success,
        "details": details,
        "response_data": response_data
    }
    st.session_state.api_call_log.append(log_entry)
    
    # Keep only last 50 entries to prevent memory issues
    if len(st.session_state.api_call_log) > 50:
        st.session_state.api_call_log = st.session_state.api_call_log[-50:]

def clean_api_key(api_key):
    """Clean API key to ensure it only contains valid characters"""
    if not api_key:
        return ""
    # Remove any non-ASCII characters and strip whitespace
    cleaned = ''.join(char for char in api_key.strip() if ord(char) < 128)
    return cleaned

def validate_ada_connection(instance_name, api_key):
    """Validate Ada API connection by testing the knowledge sources endpoint"""
    if not all([instance_name, api_key]):
        return False, "Missing instance name or API key"
    
    # Clean the API key
    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()
    
    if not api_key:
        return False, "API key contains invalid characters"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        log_api_call(
            method="GET",
            url=url,
            status_code=response.status_code,
            success=response.status_code == 200,
            details="Validate Ada API connection"
        )
        
        if response.status_code == 200:
            return True, "Connection successful"
        elif response.status_code == 401:
            return False, "Invalid API key"
        elif response.status_code == 403:
            return False, "Access forbidden - check API permissions"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except requests.exceptions.Timeout:
        return False, "Connection timeout - check instance name"
    except requests.exceptions.ConnectionError:
        return False, "Connection error - check instance name and internet connection"
    except UnicodeEncodeError:
        return False, "API key contains invalid characters. Please check your API key."
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

def generate_source_id():
    """Generate a random source ID compatible with Ada API"""
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

def clean_html_to_markdown(html_content):
    """Clean HTML content and convert to markdown"""
    if not html_content:
        return ""
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False
        h.body_width = 0
        h.unicode_snob = True
        h.ignore_tables = False
        
        markdown_content = h.handle(str(soup))
        markdown_content = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown_content)
        markdown_content = markdown_content.strip()
        
        return markdown_content
    except Exception as e:
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text().strip()

def is_empty_article(article):
    """Check if an article has empty or minimal content"""
    content = article.get('body', '')
    if not content:
        return True, "Article has no content"
    
    cleaned_content = clean_html_to_markdown(content).strip()
    if len(cleaned_content) < 20:
        return True, f"Article has minimal content ({len(cleaned_content)} characters)"
    
    if not cleaned_content or cleaned_content.isspace():
        return True, "Article contains only whitespace"
    
    return False, ""

@st.cache_data
def fetch_grab_data(user_type, language_locale):
    """Fetch data from Grab help articles API"""
    # MoveIt always uses driver endpoint with en-ph locale
    if user_type == "moveit":
        url = "https://help.grab.com/articles/v4/driver/en-ph.json"
    else:
        url = f"https://help.grab.com/articles/v4/{user_type}/{language_locale}.json"
    
    try:
        response = requests.get(url, timeout=30)
        
        log_api_call(
            method="GET",
            url=url,
            status_code=response.status_code,
            success=response.status_code == 200,
            details=f"Fetch Grab articles for {user_type}/{language_locale}"
        )
        
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        log_api_call(
            method="GET",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error fetching Grab articles: {str(e)}"
        )
        st.error(f"Error fetching data: {e}")
        return None

def extract_articles(data):
    """Extract id, uuid, name, and body from articles"""
    if not data or 'articles' not in data:
        return []
    
    articles = []
    for article in data['articles']:
        raw_body = article.get('body', '')
        cleaned_body = clean_html_to_markdown(raw_body)
        
        article_data = {
            'id': article.get('id'),
            'uuid': article.get('uuid'),
            'name': article.get('name'),
            'body': cleaned_body,
            'raw_body': raw_body,
            'parentId': article.get('parentId'),
            'caseL1': article.get('caseL1'),
            'caseL2': article.get('caseL2'),
            'caseL3': article.get('caseL3'),
            'position': article.get('position')
        }
        articles.append(article_data)
    
    return articles

def filter_moveit_articles(articles):
    """Filter articles for MoveIt based on section ID range"""
    if not articles:
        return []
    
    MOVEIT_SECTION_START = 40001122
    MOVEIT_SECTION_END = 40001341
    
    moveit_articles = []
    
    for article in articles:
        # Filter by article ID range (which represents the section IDs)
        article_id = article.get('id')
        
        if (article_id and 
            MOVEIT_SECTION_START <= article_id <= MOVEIT_SECTION_END):
            moveit_articles.append(article)
    
    return moveit_articles

def filter_articles(articles, filter_empty=True):
    """Filter out empty articles"""
    if not filter_empty:
        return articles, [], []
    
    production_articles = []
    filtered_articles = []
    analysis_results = []
    
    for article in articles:
        is_empty = False
        reasons = []
        
        if filter_empty:
            is_empty, empty_reason = is_empty_article(article)
            if is_empty:
                reasons.append(f"Empty: {empty_reason}")
        
        should_filter = filter_empty and is_empty
        
        analysis_results.append({
            'id': article['id'],
            'name': article['name'],
            'is_filtered': should_filter,
            'is_empty': is_empty,
            'reasons': reasons,
            'article': article
        })
        
        if should_filter:
            filtered_articles.append(article)
        else:
            production_articles.append(article)
    
    return production_articles, filtered_articles, analysis_results

def delete_ada_article(instance_name, api_key, article_id):
    """Delete a single article from Ada knowledge base"""
    if not all([instance_name, api_key, article_id]):
        return False, "Missing required parameters"
    
    # Clean inputs
    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()
    
    if not api_key:
        return False, "API key contains invalid characters"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/articles/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    params = {
        "id": article_id
    }
    
    try:
        response = requests.delete(url, headers=headers, params=params, timeout=30)
        
        log_api_call(
            method="DELETE",
            url=f"{url}?id={article_id}",
            status_code=response.status_code,
            success=response.status_code in [200, 204],
            details=f"Delete Ada article ID: {article_id}"
        )
        
        if response.status_code in [200, 204]:
            return True, "Article deleted successfully"
        else:
            return False, f"HTTP {response.status_code}: {response.text}"
            
    except UnicodeEncodeError:
        return False, "API key contains invalid characters"
    except requests.exceptions.RequestException as e:
        log_api_call(
            method="DELETE",
            url=f"{url}?id={article_id}",
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error deleting Ada article {article_id}: {str(e)}"
        )
        return False, f"Error deleting article: {str(e)}"

def compare_articles(grab_articles, ada_articles):
    """Enhanced comparison of Grab articles with Ada articles using numeric ID extraction"""
    import re
    
    def extract_numeric_id(article_id):
        """Extract only numeric part from article ID using regex"""
        if not article_id:
            return ""
        # Extract all digits from the ID
        numeric_match = re.search(r'(\d+)', str(article_id))
        return numeric_match.group(1) if numeric_match else str(article_id)
    
    # Create ID sets with numeric extraction
    grab_ids = set()
    ada_ids = set()
    
    # Store mapping of numeric ID to original article for reference
    grab_id_mapping = {}
    ada_id_mapping = {}
    
    for article in grab_articles:
        if article.get('id'):
            original_id = str(article['id']).strip()
            numeric_id = extract_numeric_id(original_id)
            grab_ids.add(numeric_id)
            grab_id_mapping[numeric_id] = original_id
    
    for article in ada_articles:
        if article.get('id'):
            original_id = str(article['id']).strip()
            numeric_id = extract_numeric_id(original_id)
            ada_ids.add(numeric_id)
            ada_id_mapping[numeric_id] = original_id
    
    # Create name sets for additional validation
    grab_names = set()
    ada_names = set()
    
    for article in grab_articles:
        if article.get('name'):
            clean_name = article['name'].strip()
            grab_names.add(clean_name)
    
    for article in ada_articles:
        if article.get('name'):
            clean_name = article['name'].strip()
            ada_names.add(clean_name)
    
    # Find matches
    existing_by_id = grab_ids.intersection(ada_ids)
    existing_by_name = grab_names.intersection(ada_names)
    
    # Categorize articles
    existing_articles = []
    new_articles = []
    
    for article in grab_articles:
        original_id = str(article['id']).strip() if article.get('id') else ''
        numeric_id = extract_numeric_id(original_id)
        article_name = article.get('name', '').strip()
        
        # Check if exists by numeric ID or name
        exists_by_id = numeric_id in existing_by_id
        exists_by_name = article_name in existing_by_name
        
        if exists_by_id or exists_by_name:
            existing_articles.append(article)
        else:
            new_articles.append(article)
    
    # Find missing articles (in Ada but not in Grab) - using numeric IDs
    ada_numeric_ids_not_in_grab = ada_ids - grab_ids
    missing_articles = []
    for article in ada_articles:
        if article.get('id'):
            original_id = str(article['id']).strip()
            numeric_id = extract_numeric_id(original_id)
            if numeric_id in ada_numeric_ids_not_in_grab:
                missing_articles.append(article)
    
    return {
        'existing': existing_articles,
        'new': new_articles,
        'missing': missing_articles,
        'debug_info': {
            'grab_ids_count': len(grab_ids),
            'ada_ids_count': len(ada_ids),
            'matched_by_id': len(existing_by_id),
            'matched_by_name_only': len(existing_by_name - existing_by_id)
        }
    }

def convert_to_ada_format(articles, user_type, language_locale, knowledge_source_id, override_language=None, name_prefix=None, id_prefix=None):
    """Convert articles to Ada JSON format"""
    ada_articles = []
    
    language_to_use = override_language if override_language else language_locale
    
    for article in articles:
        # Generate URL based on user type
        if user_type == "moveit":
            # MoveIt articles use driver/en-ph path on help.grab.com
            article_url = f"https://help.grab.com/driver/en-ph/{article['id']}"
        else:
            article_url = f"https://help.grab.com/{user_type}/{language_locale}/{article['id']}"
        
        # Prepare article name with optional prefix
        article_name = article['name'] or f"Article {article['id']}"
        if name_prefix:
            article_name = f"{name_prefix}{article_name}"
        
        # Prepare article ID with optional prefix
        article_id = str(article['id'])
        if id_prefix:
            article_id = f"{id_prefix}{article_id}"
        
        # Generate current timestamp in required format
        external_updated = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        ada_article = {
            "id": article_id,
            "name": article_name,
            "content": article['body'] or "",
            "knowledge_source_id": knowledge_source_id,
            "url": article_url,
            "language": language_to_use,
            "external_updated": external_updated
        }
        ada_articles.append(ada_article)
    
    return ada_articles

def create_ada_article_with_status(instance_name, api_key, article_data, status_container, index, total):
    """Create a single article in Ada using bulk endpoint with rate limiting and retry."""
    if not all([instance_name, api_key]):
        return False, "Missing configuration"

    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()

    if not api_key:
        return False, "API key contains invalid characters"

    article_name = article_data.get('name', 'Unknown')
    article_id = article_data.get('id', 'Unknown')

    with status_container.container():
        st.write(f"🔄 **Creating article {index}/{total}:** {article_name[:60]}{'...' if len(article_name) > 60 else ''}")
        st.write(f"📋 **Article ID:** `{article_id}`")

    url = f"https://{instance_name}.ada.support/api/v2/knowledge/bulk/articles/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = [article_data]

    for attempt in range(MAX_RETRIES + 1):
        try:
            enforce_rate_limit()
            start_time = time.time()
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            end_time = time.time()

            log_api_call(
                method="POST",
                url=url,
                status_code=response.status_code,
                success=response.status_code in [200, 201],
                details=f"Create article '{article_name}' (ID: {article_id}), attempt {attempt + 1}"
            )

            if response.status_code in [200, 201]:
                with status_container.container():
                    st.success(f"✅ **Successfully created:** {article_name}")
                    st.write(f"⏱️ **Response Time:** {end_time - start_time:.2f}s")
                    if attempt > 0:
                        st.write(f"🔁 **Succeeded on attempt {attempt + 1}**")
                    st.write("---")
                return True, response.json()

            # Non-retryable client error or retries exhausted
            if response.status_code not in RETRYABLE_STATUS_CODES or attempt == MAX_RETRIES:
                error_detail = ""
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text
                with status_container.container():
                    st.error(f"❌ **Failed to create:** {article_name}")
                    st.write(f"🚨 **Error Code:** {response.status_code}")
                    st.write(f"📝 **Error Details:** {error_detail}")
                    st.write("---")
                return False, f"HTTP {response.status_code}: {error_detail}"

            # Calculate wait before retry
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else min(
                    RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), RETRY_MAX_DELAY
                )
                with status_container.container():
                    st.warning(f"⏳ **Rate limited (429).** Waiting {wait:.1f}s before retry {attempt + 1}/{MAX_RETRIES}...")
            else:
                wait = min(RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), RETRY_MAX_DELAY)
                with status_container.container():
                    st.warning(f"⚠️ **HTTP {response.status_code}.** Retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)

        except requests.exceptions.Timeout:
            if attempt == MAX_RETRIES:
                with status_container.container():
                    st.error(f"⏰ **Timeout creating:** {article_name} (all {MAX_RETRIES} retries exhausted)")
                    st.write("---")
                log_api_call(method="POST", url=url, status_code=0, success=False,
                             details=f"Timeout creating '{article_name}' after {MAX_RETRIES} retries")
                return False, "Request timed out after retries"
            wait = min(RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), RETRY_MAX_DELAY)
            with status_container.container():
                st.warning(f"⏰ **Timeout.** Retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)

        except UnicodeEncodeError:
            return False, "API key contains invalid characters"

        except requests.exceptions.RequestException as e:
            if attempt == MAX_RETRIES:
                with status_container.container():
                    st.error(f"❌ **Network error creating:** {article_name}")
                    st.write(f"🚨 **Error:** {str(e)}")
                    st.write("---")
                log_api_call(
                    method="POST", url=url,
                    status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
                    success=False,
                    details=f"Error creating '{article_name}': {str(e)}"
                )
                return False, f"Error: {e}"
            wait = min(RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1), RETRY_MAX_DELAY)
            with status_container.container():
                st.warning(f"⚠️ **Network error.** Retrying in {wait:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
            time.sleep(wait)

    return False, "Max retries exceeded"

def create_articles_individually_with_status(articles, instance_name, knowledge_source_id, api_key, user_type, language_locale, override_language=None, name_prefix=None, id_prefix=None):
    """Create articles in Ada knowledge base with real-time status updates"""
    if not all([instance_name, knowledge_source_id, api_key]):
        return False, "Missing configuration"
    
    # Clean inputs
    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()
    
    if not api_key:
        return False, "API key contains invalid characters"
    
    ada_articles = convert_to_ada_format(articles, user_type, language_locale, knowledge_source_id, override_language, name_prefix, id_prefix)
    
    successful_uploads = []
    failed_uploads = []
    
    main_progress = st.progress(0)
    main_status = st.empty()
    status_container = st.container()
    metrics_container = st.container()
    
    log_api_call(
        method="POST",
        url="Individual Article Creation Process",
        status_code=200,
        success=True,
        details=f"Starting individual creation of {len(ada_articles)} articles"
    )
    
    start_time = time.time()
    
    for i, article_data in enumerate(ada_articles):
        progress = (i + 1) / len(ada_articles)
        main_progress.progress(progress)
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        with main_status:
            st.write(f"🚀 **Processing article {i+1} of {len(ada_articles)}**")
        
        with metrics_container:
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("✅ Successful", len(successful_uploads))
            with col2:
                st.metric("❌ Failed", len(failed_uploads))
            with col3:
                st.metric("📊 Progress", f"{progress*100:.1f}%")
            with col4:
                st.metric("⏱️ Elapsed", f"{elapsed_time:.1f}s")
        
        success, result = create_ada_article_with_status(
            instance_name, api_key, article_data, status_container, i+1, len(ada_articles)
        )
        
        if success:
            successful_uploads.append({
                "article": article_data,
                "response": result
            })
        else:
            failed_uploads.append({
                "article": article_data,
                "error": result
            })
        
        # Rate limiting is now handled inside create_ada_article_with_status

    main_progress.progress(1.0)
    total_time = time.time() - start_time
    
    with main_status:
        st.write(f"🎉 **Upload process completed in {total_time:.1f} seconds!**")
    
    log_api_call(
        method="POST",
        url="Individual Article Creation Complete",
        status_code=200,
        success=True,
        details=f"Completed individual article creation: {len(successful_uploads)} successful, {len(failed_uploads)} failed"
    )
    
    return True, {
        "successful": len(successful_uploads),
        "failed": len(failed_uploads),
        "successful_uploads": successful_uploads,
        "failed_uploads": failed_uploads,
        "total_processed": len(ada_articles),
        "total_time": total_time
    }

def create_ada_knowledge_source(instance_name, api_key, source_name, current_user_type, current_language_locale):
    """Create a new knowledge source in Ada"""
    if not all([instance_name, api_key, source_name]):
        return False, "Missing required fields"
    
    # Clean inputs
    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()
    
    if not api_key:
        return False, "API key contains invalid characters"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    source_id = generate_source_id()
    
    payload = {
        "id": source_id,
        "name": source_name
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        log_api_call(
            method="POST",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 201],
            details=f"Create knowledge source '{source_name}' with ID '{source_id}'"
        )
        
        response.raise_for_status()
        result = response.json()
        
        returned_source_id = result.get('data', {}).get('id', source_id)
        
        return True, {"source_id": returned_source_id, "response": result}
    except UnicodeEncodeError:
        return False, "API key contains invalid characters"
    except requests.exceptions.RequestException as e:
        error_detail = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
        
        log_api_call(
            method="POST",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error creating knowledge source '{source_name}': {str(e)}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"

def list_ada_knowledge_sources(instance_name, api_key):
    """List all knowledge sources in Ada"""
    if not all([instance_name, api_key]):
        return False, "Missing required fields"
    
    # Clean inputs
    api_key = clean_api_key(api_key)
    instance_name = instance_name.strip()
    
    if not api_key:
        return False, "API key contains invalid characters"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        log_api_call(
            method="GET",
            url=url,
            status_code=response.status_code,
            success=response.status_code == 200,
            details="List all knowledge sources"
        )
        
        response.raise_for_status()
        return True, response.json()
    except UnicodeEncodeError:
        return False, "API key contains invalid characters"
    except requests.exceptions.RequestException as e:
        log_api_call(
            method="GET",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error listing knowledge sources: {str(e)}"
        )
        return False, f"Error: {e}"

# Sidebar Configuration
st.sidebar.header("Configuration")

# Simple Ada API Configuration
st.sidebar.subheader("🔐 Ada API Configuration")
instance_name = st.sidebar.text_input("Instance Name (without .ada.support):")
api_key = st.sidebar.text_input("API Key:", type="password")

# Test connection button
if instance_name and api_key and st.sidebar.button("🔄 Test Connection"):
    with st.sidebar.spinner("Testing connection..."):
        success, message = validate_ada_connection(instance_name, api_key)
        if success:
            st.sidebar.success(f"✅ {message}")
        else:
            st.sidebar.error(f"❌ {message}")

# Show current configuration status
if instance_name and api_key:
    st.sidebar.success("🟢 Ada API configured")
else:
    st.sidebar.warning("🟡 Ada API not configured")

# Grab API Parameters
st.sidebar.subheader("Grab API Parameters")
user_type = st.sidebar.selectbox(
    "Select User Type:",
    ["passenger", "driver", "merchant", "moveit"]
)

language_locale = st.sidebar.text_input(
    "Language-Locale (e.g., en-ph):",
    value="en-ph"
)

# Show info for MoveIt
if user_type == "moveit":
    st.sidebar.info("📍 MoveIt always uses driver/en-ph endpoint and filters articles with IDs 40001122-40001341")

# Article filtering options
st.sidebar.subheader("Article Filters")
filter_empty = st.sidebar.checkbox("Filter out empty articles", value=True)

# Ada Payload Options
st.sidebar.subheader("🔧 Ada Payload Options")

# Language Override
override_language_enabled = st.sidebar.checkbox("Override Language Code", value=False)
if override_language_enabled:
    override_language = st.sidebar.text_input("Custom Language Code:", value=language_locale)
else:
    override_language = None

# Name Prefix
name_prefix_enabled = st.sidebar.checkbox("Add Name Prefix", value=False)
if name_prefix_enabled:
    name_prefix = st.sidebar.text_input("Name Prefix:", placeholder="e.g., 'Production - '")
else:
    name_prefix = None

# ID Prefix
id_prefix_enabled = st.sidebar.checkbox("Add ID Prefix", value=False)
if id_prefix_enabled:
    id_prefix = st.sidebar.text_input("ID Prefix:", placeholder="e.g., 'prod_', 'v1_'")
else:
    id_prefix = None

# Knowledge Source Management
st.header("🗂️ Knowledge Source Management")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Create New Knowledge Source")
    new_source_name = st.text_input(
        "Knowledge Source Name:",
        placeholder=f"e.g., 'Grab {user_type.title()} Help - {language_locale.upper()}'"
    )
    
    if st.button("Create Knowledge Source"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings first")
        elif not new_source_name:
            st.error("Please enter a knowledge source name")
        else:
            with st.spinner("Creating knowledge source..."):
                success, result = create_ada_knowledge_source(
                    instance_name, api_key, new_source_name, user_type, language_locale
                )
                
                if success:
                    st.success(f"✅ Knowledge source created successfully!")
                    st.write(f"**Source ID:** `{result['source_id']}`")
                    st.session_state.selected_knowledge_source_id = result['source_id']
                else:
                    st.error(f"❌ Failed to create knowledge source: {result}")

with col2:
    st.subheader("List Knowledge Sources")
    
    if st.button("List Knowledge Sources"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings first")
        else:
            with st.spinner("Fetching knowledge sources..."):
                success, result = list_ada_knowledge_sources(instance_name, api_key)
                
                if success:
                    if 'data' in result and result['data']:
                        st.success(f"✅ Found {len(result['data'])} knowledge sources")
                        
                        sources_df = pd.DataFrame(result['data'])
                        st.dataframe(sources_df[['id', 'name']])
                        
                        source_options = [f"{source['name']} ({source['id']})" for source in result['data']]
                        selected_source_display = st.selectbox(
                            "Select a knowledge source:",
                            ["Select..."] + source_options
                        )
                        
                        if selected_source_display != "Select...":
                            selected_source_id = selected_source_display.split("(")[-1].replace(")", "")
                            st.success(f"Selected Source ID: `{selected_source_id}`")
                            st.session_state.selected_knowledge_source_id = selected_source_id
                    else:
                        st.info("No knowledge sources found")
                else:
                    st.error(f"❌ Failed to fetch knowledge sources: {result}")

st.divider()

# Article Retrieval
st.header("📥 Fetch Articles from Grab")

# Display the URL that will be fetched
if user_type == "moveit":
    current_url = "https://help.grab.com/articles/v4/driver/en-ph.json"
else:
    current_url = f"https://help.grab.com/articles/v4/{user_type}/{language_locale}.json"
st.write(f"**API URL:** {current_url}")

if st.button("🔄 Fetch Articles from Grab", type="primary"):
    with st.spinner("Fetching articles from Grab..."):
        data = fetch_grab_data(user_type, language_locale)
        
        if data:
            all_articles = extract_articles(data)
            
            # Apply MoveIt filtering if needed
            if user_type == "moveit":
                original_count = len(all_articles)
                all_articles = filter_moveit_articles(all_articles)
                st.info(f"📍 MoveIt Filter: {len(all_articles)} articles (IDs 40001122-40001341) out of {original_count} total")
            
            if all_articles:
                production_articles, filtered_articles, analysis = filter_articles(
                    all_articles, filter_empty
                )
                
                st.session_state.all_articles = all_articles
                st.session_state.production_articles = production_articles
                st.session_state.filtered_articles = filtered_articles
                st.session_state.analysis = analysis
                st.session_state.user_type = user_type
                st.session_state.language_locale = language_locale
                
                st.success(f"✅ **Successfully fetched {len(all_articles)} total articles**")
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📄 Total Articles", len(all_articles))
                with col2:
                    st.metric("✅ Production Articles", len(production_articles))
                with col3:
                    st.metric("🚫 Filtered Articles", len(filtered_articles))
                
                if production_articles:
                    st.subheader("Production Articles Preview")
                    preview_data = []
                    for article in production_articles[:5]:
                        preview_data.append({
                            'ID': article['id'],
                            'Name': article['name'],
                            'Content Length': len(article['body'])
                        })
                    
                    preview_df = pd.DataFrame(preview_data)
                    st.dataframe(preview_df)
                else:
                    st.warning("No production articles found after filtering")
            else:
                st.warning("No articles found in the response")
        else:
            st.error("Failed to fetch data. Please check your parameters.")

if 'production_articles' in st.session_state:
    articles_to_use = st.session_state.production_articles
    st.info(f"📋 {len(articles_to_use)} articles ready for comparison and upload to Ada")

st.divider()

# Article Comparison Section with FIXED pagination
st.header("🔍 Compare with Ada Knowledge Base")

if 'production_articles' in st.session_state:
    comparison_knowledge_source_id = st.text_input(
        "Knowledge Source ID for Comparison:",
        value=st.session_state.get('selected_knowledge_source_id', ''),
        help="Enter the ID of the knowledge source to compare with"
    )
    
    if st.button("🔍 Compare Articles", type="secondary"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings first")
        elif not comparison_knowledge_source_id:
            st.error("Please enter a Knowledge Source ID for comparison")
        else:
            st.header("🔄 Real-Time Comparison Process")
            
            # Live status containers
            main_progress = st.progress(0)
            main_status = st.empty()
            fetch_container = st.container()
            comparison_container = st.container()
            
            # Step 1: Fetch Ada articles with live updates
            with main_status:
                st.write("📡 **Step 1/2:** Fetching articles from Ada knowledge base...")
            main_progress.progress(0.25)
            
            all_ada_articles = []
            page = 1
            total_fetched = 0
            
            with fetch_container:
                st.subheader("📡 Fetching Ada Articles")
                page_status = st.empty()
                articles_status = st.empty()
            
            # Clean inputs
            api_key_clean = clean_api_key(api_key)
            instance_name_clean = instance_name.strip()
            
            if not api_key_clean:
                st.error("API key contains invalid characters")
            else:
                # FIXED Pagination Logic
                current_url = f"https://{instance_name_clean}.ada.support/api/v2/knowledge/articles/"
                
                while current_url:  # Continue while we have a URL to fetch
                    headers = {
                        "Authorization": f"Bearer {api_key_clean}",
                        "Content-Type": "application/json"
                    }
                    
                    # Only add knowledge_source_id parameter on first request
                    # Subsequent requests use the full next_page_url
                    if page == 1:
                        params = {
                            "knowledge_source_id": comparison_knowledge_source_id
                        }
                    else:
                        params = {}  # next_page_url already contains all necessary parameters
                    
                    with page_status:
                        st.write(f"🔄 **Fetching page {page}...**")
                        if page > 1:
                            st.write(f"📍 **URL:** `{current_url[:80]}...`")
                    
                    try:
                        start_time = time.time()
                        if page == 1:
                            response = requests.get(current_url, headers=headers, params=params, timeout=30)
                        else:
                            # Use the next_page_url directly (it already contains all parameters)
                            response = requests.get(current_url, headers=headers, timeout=30)
                        end_time = time.time()
                        
                        log_api_call(
                            method="GET",
                            url=current_url if page > 1 else f"{current_url}?knowledge_source_id={comparison_knowledge_source_id}",
                            status_code=response.status_code,
                            success=response.status_code == 200,
                            details=f"Fetch Ada articles page {page}"
                        )
                        
                        if response.status_code != 200:
                            with page_status:
                                st.error(f"❌ **Failed to fetch page {page}:** HTTP {response.status_code}")
                            st.error(f"Failed to fetch articles from Ada: {response.text}")
                            break
                        
                        data = response.json()
                        articles = data.get('data', [])
                        
                        # Add articles if we have them
                        if articles:
                            all_ada_articles.extend(articles)
                            total_fetched += len(articles)
                            
                            with page_status:
                                st.success(f"✅ **Page {page} fetched:** {len(articles)} articles ({end_time - start_time:.2f}s)")
                        else:
                            with page_status:
                                st.info(f"ℹ️ **Page {page} returned 0 articles**")
                        
                        with articles_status:
                            col1, col2 = st.columns(2)
                            with col1:
                                st.metric("📊 Total Articles Fetched", total_fetched)
                            with col2:
                                st.metric("📄 Current Page", page)
                        
                        # Check for next page using next_page_url
                        meta = data.get('meta', {})
                        current_url = meta.get('next_page_url')  # This becomes None when no more pages
                        
                        if not current_url:
                            with page_status:
                                st.info(f"✅ **No next_page_url found - pagination complete**")
                            break
                        
                        # Move to next page
                        page += 1
                        time.sleep(0.1)  # Small delay between requests
                            
                    except UnicodeEncodeError:
                        with page_status:
                            st.error(f"❌ **Unicode error on page {page}:** API key contains invalid characters")
                        break
                    except requests.exceptions.RequestException as e:
                        log_api_call(
                            method="GET",
                            url=current_url,
                            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
                            success=False,
                            details=f"Error fetching Ada articles page {page}: {str(e)}"
                        )
                        
                        with page_status:
                            st.error(f"❌ **Error fetching page {page}:** {str(e)}")
                        st.error(f"Error fetching articles from Ada: {str(e)}")
                        break
                
                # Show final fetch summary
                with page_status:
                    if total_fetched > 0:
                        st.success(f"🎉 **Pagination complete! Fetched {total_fetched} articles from {page-1} pages**")
                    else:
                        st.warning(f"⚠️ **No articles found in knowledge source `{comparison_knowledge_source_id}`**")
            
            if all_ada_articles:
                with main_status:
                    st.write("🔍 **Step 2/2:** Analyzing and comparing articles...")
                main_progress.progress(0.75)
                
                with comparison_container:
                    # Perform enhanced comparison
                    grab_articles = st.session_state.production_articles
                    comparison = compare_articles(grab_articles, all_ada_articles)
                    
                    # Store comparison results
                    st.session_state.comparison_results = comparison
                    st.session_state.comparison_knowledge_source_id = comparison_knowledge_source_id
                
                main_progress.progress(1.0)
                
                with main_status:
                    st.write("🎉 **Comparison process completed successfully!**")
                
                # Display comparison results
                st.header("📊 Comparison Results")
                
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("🔄 Articles to Update", len(comparison['existing']))
                with col2:
                    st.metric("🆕 New Articles", len(comparison['new']))
                with col3:
                    st.metric("❌ Missing/Orphaned", len(comparison['missing']))
                
                # Performance metrics
                st.subheader("⚡ Process Performance")
                perf_col1, perf_col2, perf_col3 = st.columns(3)
                with perf_col1:
                    st.metric("📄 Ada Articles Fetched", len(all_ada_articles))
                with perf_col2:
                    st.metric("📄 Grab Articles Analyzed", len(grab_articles))
                with perf_col3:
                    st.metric("📊 Pages Fetched", page - 1)
                
                # Show details in expandable sections
                with st.expander(f"🔄 Articles to Update ({len(comparison['existing'])})"):
                    if comparison['existing']:
                        existing_df = pd.DataFrame([{
                            'ID': article['id'],
                            'Name': article['name'],
                            'Content Length': len(article['body'])
                        } for article in comparison['existing']])
                        st.dataframe(existing_df)
                    else:
                        st.info("No existing articles found")
                
                with st.expander(f"🆕 New Articles to Upload ({len(comparison['new'])})"):
                    if comparison['new']:
                        new_df = pd.DataFrame([{
                            'ID': article['id'],
                            'Name': article['name'],
                            'Content Length': len(article['body'])
                        } for article in comparison['new']])
                        st.dataframe(new_df)
                    else:
                        st.info("No new articles to upload")
                
                with st.expander(f"❌ Missing/Orphaned Articles ({len(comparison['missing'])})"):
                    if comparison['missing']:
                        missing_df = pd.DataFrame([{
                            'ID': article.get('id', 'Unknown'),
                            'Name': article.get('name', 'Unknown'),
                            'Language': article.get('language', 'Unknown')
                        } for article in comparison['missing']])
                        st.dataframe(missing_df)
                        
                        # Delete missing articles section
                        st.subheader("🗑️ Delete Missing Articles")
                        st.warning("These articles exist in Ada but not in the current Grab scrape. They may be outdated.")
                        
                        # Create checkboxes for each missing article (all checked by default)
                        articles_to_delete = []
                        for i, article in enumerate(comparison['missing']):
                            article_name = article.get('name', 'Unknown')
                            article_id = article.get('id', 'Unknown')
                            
                            # All checkboxes checked by default
                            if st.checkbox(
                                f"Delete: {article_name} (ID: {article_id})", 
                                value=True, 
                                key=f"delete_{i}"
                            ):
                                articles_to_delete.append(article)
                        
                        if articles_to_delete and st.button("🗑️ Delete Selected Articles", type="secondary"):
                            st.subheader("🔄 Real-Time Deletion Progress")
                            
                            delete_progress = st.progress(0)
                            delete_main_status = st.empty()
                            delete_metrics_container = st.container()
                            delete_status_container = st.container()
                            
                            successful_deletes = 0
                            failed_deletes = 0
                            
                            with delete_main_status:
                                st.write(f"🗑️ **Starting deletion of {len(articles_to_delete)} articles...**")
                            
                            for i, article in enumerate(articles_to_delete):
                                progress = (i + 1) / len(articles_to_delete)
                                delete_progress.progress(progress)
                                
                                article_name = article.get('name', 'Unknown')
                                article_id = article.get('id', 'Unknown')
                                
                                with delete_main_status:
                                    st.write(f"🗑️ **Deleting {i+1}/{len(articles_to_delete)}:** {article_name[:50]}{'...' if len(article_name) > 50 else ''}")
                                
                                with delete_metrics_container:
                                    col1, col2, col3 = st.columns(3)
                                    with col1:
                                        st.metric("✅ Successful", successful_deletes)
                                    with col2:
                                        st.metric("❌ Failed", failed_deletes)
                                    with col3:
                                        st.metric("📊 Progress", f"{progress*100:.1f}%")
                                
                                with delete_status_container.container():
                                    st.write(f"🔄 **Processing:** {article_name}")
                                    st.write(f"📋 **Article ID:** `{article_id}`")
                                
                                start_time = time.time()
                                success, message = delete_ada_article(instance_name_clean, api_key_clean, article_id)
                                end_time = time.time()
                                
                                if success:
                                    successful_deletes += 1
                                    with delete_status_container.container():
                                        st.success(f"✅ **Successfully deleted:** {article_name}")
                                        st.write(f"⏱️ **Response Time:** {end_time - start_time:.2f} seconds")
                                        st.write("---")
                                else:
                                    failed_deletes += 1
                                    with delete_status_container.container():
                                        st.error(f"❌ **Failed to delete:** {article_name}")
                                        st.write(f"🚨 **Error:** {message}")
                                        st.write(f"⏱️ **Response Time:** {end_time - start_time:.2f} seconds")
                                        st.write("---")
                                
                                time.sleep(0.1)  # Small delay to prevent overwhelming the API
                            
                            delete_progress.progress(1.0)
                            
                            with delete_main_status:
                                st.write("🎉 **Deletion process completed!**")
                            
                            # Final summary
                            st.subheader("📊 Deletion Summary")
                            summary_col1, summary_col2, summary_col3 = st.columns(3)
                            with summary_col1:
                                st.metric("✅ Successfully Deleted", successful_deletes)
                            with summary_col2:
                                st.metric("❌ Failed to Delete", failed_deletes)
                            with summary_col3:
                                delete_success_rate = (successful_deletes / len(articles_to_delete)) * 100 if articles_to_delete else 0
                                st.metric("📊 Success Rate", f"{delete_success_rate:.1f}%")
                            
                            if successful_deletes > 0:
                                st.balloons()
                                st.success(f"🎉 Successfully deleted {successful_deletes} orphaned articles from Ada!")
                    else:
                        st.info("No missing/orphaned articles found")
            else:
                main_progress.progress(1.0)
                with main_status:
                    st.write("❌ **Comparison failed - no articles fetched from Ada**")
                st.error("Failed to fetch articles from Ada knowledge base or knowledge source is empty")
else:
    st.info("👆 Please fetch articles from Grab first before comparing")

st.divider()

# Upload to Ada
st.header("📤 Upload Articles to Ada")

# Determine which articles to upload - always allow upload
articles_to_upload = None
upload_description = ""

if 'comparison_results' in st.session_state:
    # Combine existing (for update) and new articles
    existing_articles = st.session_state.comparison_results['existing']
    new_articles = st.session_state.comparison_results['new']
    articles_to_upload = existing_articles + new_articles
    
    if existing_articles and new_articles:
        upload_description = f"📋 {len(articles_to_upload)} articles ready for upload ({len(existing_articles)} to update + {len(new_articles)} new)"
    elif existing_articles:
        upload_description = f"📋 {len(articles_to_upload)} articles ready for update (no new articles)"
    elif new_articles:
        upload_description = f"📋 {len(articles_to_upload)} new articles ready for upload"
    else:
        upload_description = "📋 No articles to upload or update"
        
elif 'production_articles' in st.session_state:
    # Use all production articles
    articles_to_upload = st.session_state.production_articles
    upload_description = f"📋 {len(articles_to_upload)} articles ready for upload (all production articles)"

if articles_to_upload is not None:  # Always show upload section if we have any articles
    st.info(upload_description)
    
    st.write(f"**Ready to upload {len(articles_to_upload)} articles to Ada**")
    
    # Auto-populate knowledge source ID
    default_upload_id = ""
    if 'comparison_knowledge_source_id' in st.session_state:
        default_upload_id = st.session_state.comparison_knowledge_source_id
    elif 'selected_knowledge_source_id' in st.session_state:
        default_upload_id = st.session_state.selected_knowledge_source_id
    
    knowledge_source_id = st.text_input(
        "Knowledge Source ID:", 
        value=default_upload_id,
        help="Enter the ID of the knowledge source where articles will be uploaded"
    )
    
    if default_upload_id:
        st.info("💡 Knowledge Source ID auto-filled from your selection above")
    
    # Show current configuration
    st.subheader("🔧 Upload Configuration")
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.write("**Language Settings:**")
        if override_language_enabled and override_language:
            st.write(f"🔄 Custom: `{override_language}`")
        else:
            st.write(f"📍 Default: `{language_locale}`")
    
    with col2:
        st.write("**Name Settings:**")
        if name_prefix_enabled and name_prefix:
            st.write(f"🏷️ Prefix: `{name_prefix}`")
        else:
            st.write("📝 No prefix")
    
    with col3:
        st.write("**ID Settings:**")
        if id_prefix_enabled and id_prefix:
            st.write(f"🆔 Prefix: `{id_prefix}`")
        else:
            st.write("📝 No prefix")
    
    # Preview
    if st.checkbox("🔍 Preview data that will be sent to Ada"):
        if articles_to_upload and knowledge_source_id:
            sample_ada_data = convert_to_ada_format(
                articles_to_upload[:2], 
                st.session_state.user_type, 
                st.session_state.language_locale,
                knowledge_source_id,
                override_language,
                name_prefix,
                id_prefix
            )
            
            if sample_ada_data:
                st.write("**Sample Article Structure:**")
                st.json(sample_ada_data[0])
                
                # Show summary
                preview_summary = []
                for article in sample_ada_data:
                    preview_summary.append({
                        'Article ID': article['id'],
                        'Name': article['name'][:50] + "..." if len(article['name']) > 50 else article['name'],
                        'Content Length': len(article['content']),
                        'Language': article['language'],
                        'URL': article['url'],
                        'External Updated': article['external_updated']
                    })
                
                preview_df = pd.DataFrame(preview_summary)
                st.dataframe(preview_df)
    
    # Upload button - always enabled if we have articles
    if len(articles_to_upload) > 0 and st.button("📤 Start Upload with Live Status", type="primary"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings first")
        elif not knowledge_source_id:
            st.error("Please enter a Knowledge Source ID")
        else:
            st.header("🔄 Real-Time Upload Progress")
            st.write(f"Uploading {len(articles_to_upload)} articles to Knowledge Source: `{knowledge_source_id}`")
            
            if override_language:
                st.write(f"Using custom language: `{override_language}`")
            if name_prefix:
                st.write(f"Using name prefix: `{name_prefix}`")
            if id_prefix:
                st.write(f"Using ID prefix: `{id_prefix}`")
            
            st.write("---")
            
            success, result = create_articles_individually_with_status(
                articles_to_upload, 
                instance_name, 
                knowledge_source_id, 
                api_key,
                st.session_state.user_type,
                st.session_state.language_locale,
                override_language,
                name_prefix,
                id_prefix
            )
            
            if success:
                st.balloons()
                
                st.header("🎉 Upload Process Complete!")
                
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("✅ Successful", result['successful'])
                with col2:
                    st.metric("❌ Failed", result['failed'])
                with col3:
                    success_rate = (result['successful'] / result['total_processed']) * 100 if result['total_processed'] > 0 else 0
                    st.metric("📊 Success Rate", f"{success_rate:.1f}%")
                with col4:
                    st.metric("⏱️ Total Time", f"{result.get('total_time', 0):.1f}s")
                
                if result['successful'] > 0:
                    st.success(f"✅ Successfully uploaded {result['successful']} articles to Ada!")
                
                if result['failed'] > 0:
                    st.error(f"❌ {result['failed']} articles failed to upload")
                    
                    with st.expander(f"Failed Articles Details ({result['failed']})"):
                        for failed in result['failed_uploads']:
                            st.error(f"**{failed['article']['name']}**")
                            st.write(f"Article ID: {failed['article']['id']}")
                            st.write(f"Error: {failed['error']}")
                            st.write("---")
                
            else:
                st.error(f"❌ Failed to upload articles: {result}")
    elif len(articles_to_upload) == 0:
        st.warning("⚠️ No articles available for upload. Please fetch articles first or run a comparison.")

else:
    st.info("👆 Please fetch articles first before uploading to Ada")

st.divider()

# API Call Log
st.header("📋 API Call Log")

if st.session_state.api_call_log:
    col1, col2 = st.columns(2)
    
    with col1:
        show_successful = st.checkbox("Show Successful Calls", value=True)
        show_failed = st.checkbox("Show Failed Calls", value=True)
    
    with col2:
        if st.button("🗑️ Clear Log"):
            st.session_state.api_call_log = []
            st.success("API log cleared!")
            st.rerun()
    
    # Filter logs
    filtered_logs = []
    for log_entry in st.session_state.api_call_log:
        if (show_successful and log_entry['success']) or (show_failed and not log_entry['success']):
            filtered_logs.append(log_entry)
    
    if filtered_logs:
        successful_calls = sum(1 for log in filtered_logs if log['success'])
        failed_calls = sum(1 for log in filtered_logs if not log['success'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Calls", len(filtered_logs))
        with col2:
            st.metric("✅ Successful", successful_calls)
        with col3:
            st.metric("❌ Failed", failed_calls)
        
        st.subheader("Recent API Calls")
        
        for i, log_entry in enumerate(reversed(filtered_logs[-10:])):
            status_color = "🟢" if log_entry['success'] else "🔴"
            
            with st.container():
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col1:
                    st.write(f"{status_color} **{log_entry['method']}**")
                
                with col2:
                    display_url = log_entry['url']
                    if len(display_url) > 50:
                        display_url = display_url[:47] + "..."
                    st.write(f"`{display_url}`")
                
                with col3:
                    st.write(f"**{log_entry['status_code']}**")
                
                if log_entry['details']:
                    st.write(f"📝 {log_entry['details']}")
                
                st.divider()
        
        if len(filtered_logs) > 10:
            st.info(f"Showing last 10 calls. Total: {len(filtered_logs)} calls in log.")
    
    else:
        st.info("No API calls match your filter criteria.")

else:
    st.info("No API calls logged yet.")

# Footer
st.divider()
st.markdown("---")

col1, col2 = st.columns(2)

with col1:
    st.markdown("**Grab to Ada Knowledge Base Manager**")
    st.markdown("Built with ❤️ using Streamlit")

with col2:
    st.markdown("---")

st.markdown("*Version 5.5 - Fixed MoveIt article filtering by ID range*")
