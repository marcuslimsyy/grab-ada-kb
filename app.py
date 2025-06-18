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

# Set page title
st.title("Grab Articles to Ada Knowledge Base Manager")

# Create API keys directory
API_KEYS_DIR = Path.home() / ".grab_ada_app" / "api_keys"
API_KEYS_DIR.mkdir(parents=True, exist_ok=True)

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

def save_api_config(config_name, instance_name, api_key):
    """Save API configuration to JSON file"""
    config_data = {
        "instance_name": instance_name,
        "api_key": api_key,
        "created_date": str(pd.Timestamp.now())
    }
    
    config_file = API_KEYS_DIR / f"{config_name}.json"
    
    with open(config_file, 'w') as f:
        json.dump(config_data, f, indent=2)
    
    return True

def load_api_config(config_name):
    """Load API configuration from JSON file"""
    try:
        config_file = API_KEYS_DIR / f"{config_name}.json"
        
        if not config_file.exists():
            return None
        
        with open(config_file, 'r') as f:
            return json.load(f)
    except Exception as e:
        st.sidebar.error(f"Error loading config: {e}")
        return None

def list_saved_configs():
    """List all saved API configurations"""
    configs = []
    for file in API_KEYS_DIR.glob("*.json"):
        config_name = file.stem
        # Load config to get instance name for display
        config_data = load_api_config(config_name)
        if config_data:
            instance_name = config_data.get("instance_name", "Unknown")
            created_date = config_data.get("created_date", "Unknown")
            configs.append({
                "name": config_name,
                "instance": instance_name,
                "created": created_date
            })
    return sorted(configs, key=lambda x: x["name"])

def delete_api_config(config_name):
    """Delete a saved API configuration"""
    config_file = API_KEYS_DIR / f"{config_name}.json"
    if config_file.exists():
        config_file.unlink()
        return True
    return False

def clear_api_log():
    """Clear the API call log"""
    st.session_state.api_call_log = []
    return True

def export_api_log():
    """Export API call log as JSON"""
    if st.session_state.api_call_log:
        log_data = {
            "export_date": datetime.now().isoformat(),
            "total_calls": len(st.session_state.api_call_log),
            "calls": st.session_state.api_call_log
        }
        return json.dumps(log_data, indent=2)
    return None

def validate_ada_connection(instance_name, api_key):
    """Validate Ada API connection by testing the knowledge sources endpoint"""
    if not all([instance_name, api_key]):
        return False, "Missing instance name or API key"
    
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
            details="Validate Ada API connection",
            response_data={"connection_test": "success" if response.status_code == 200 else "failed"}
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
    except Exception as e:
        return False, f"Unexpected error: {str(e)}"

# Function to generate random source ID - UPDATED FOR ADA COMPATIBILITY
def generate_source_id():
    """Generate a random source ID compatible with Ada API"""
    # Use only lowercase letters and numbers, shorter format
    return ''.join(random.choices(string.ascii_lowercase + string.digits, k=12))

# Function to clean HTML content and convert to markdown
def clean_html_to_markdown(html_content):
    """Clean HTML content and convert to markdown"""
    if not html_content:
        return ""
    
    try:
        # Remove script and style elements
        soup = BeautifulSoup(html_content, 'html.parser')
        for script in soup(["script", "style"]):
            script.decompose()
        
        # Convert to markdown
        h = html2text.HTML2Text()
        h.ignore_links = False
        h.ignore_images = False
        h.ignore_emphasis = False
        h.body_width = 0  # Don't wrap lines
        h.unicode_snob = True
        h.ignore_tables = False
        
        # Convert HTML to markdown
        markdown_content = h.handle(str(soup))
        
        # Clean up extra whitespace
        markdown_content = re.sub(r'\n\s*\n\s*\n', '\n\n', markdown_content)
        markdown_content = markdown_content.strip()
        
        return markdown_content
    except Exception as e:
        # If conversion fails, return cleaned text
        soup = BeautifulSoup(html_content, 'html.parser')
        return soup.get_text().strip()

# Function to detect testing articles with human-readable explanations
def is_testing_article(article):
    """Detect if an article is a testing article with clear explanations"""
    
    # Common test keywords (case insensitive)
    test_keywords = [
        'test', 'testing', 'qa', 'quality assurance', 'dummy', 'sample',
        'lorem ipsum', 'placeholder', 'debug', 'dev', 'development',
        'staging', 'temp', 'temporary', 'draft', 'wip', 'work in progress',
        'do not publish', 'internal', 'beta', 'alpha', 'experiment',
        'trial', 'demo', 'example', 'mock', 'fake', 'zzz', 'xxx',
        'asdf', 'qwerty', '123test', 'test123', 'testtest'
    ]
    
    # Get article data
    article_id = str(article.get('id', ''))
    article_name = str(article.get('name', '')).lower()
    article_body = str(article.get('body', '')).lower()
    
    # Check 1: Keywords in title
    for keyword in test_keywords:
        if keyword in article_name:
            return True, f"Contains test-related word '{keyword}' in the title"
    
    # Check 2: Keywords in body (first 200 characters to avoid false positives)
    body_preview = article_body[:200]
    for keyword in test_keywords:
        if keyword in body_preview:
            return True, f"Contains test-related word '{keyword}' in the article content"
    
    # Check 3: Article ID patterns with explanations
    if re.search(r'test\d+', article_id, re.IGNORECASE):
        return True, "Article ID follows pattern 'test' + numbers (e.g., test123)"
    
    if re.search(r'\d+test', article_id, re.IGNORECASE):
        return True, "Article ID follows pattern numbers + 'test' (e.g., 123test)"
    
    if re.search(r'999\d+', article_id):
        return True, "Article ID starts with '999' which is commonly used for testing"
    
    if re.search(r'000\d+', article_id):
        return True, "Article ID starts with '000' which is commonly used for testing"
    
    if re.search(r'123456789', article_id):
        return True, "Article ID contains sequential numbers (123456789) which suggests testing"
    
    if re.search(r'987654321', article_id):
        return True, "Article ID contains reverse sequential numbers (987654321) which suggests testing"
    
    # Check 4: Very short or empty content
    if len(article_body.strip()) < 10:
        return True, "Article has very little content (less than 10 characters)"
    
    # Check 5: Title patterns that suggest testing
    if re.search(r'^(test|sample|dummy|placeholder)\s', article_name):
        return True, "Title starts with a test-related word (test, sample, dummy, or placeholder)"
    
    # Check 6: Repeated characters
    if re.search(r'(.)\1{4,}', article_name):
        return True, "Title contains repeated characters (like 'aaaaa' or '11111') which suggests testing"
    
    if re.search(r'12345|abcde|qwert', article_name):
        return True, "Title contains keyboard sequences (12345, abcde, qwert) which suggests testing"
    
    return False, ""

# Function to check if article is empty
def is_empty_article(article):
    """Check if an article has empty or minimal content"""
    content = article.get('body', '')
    if not content:
        return True, "Article has no content"
    
    # Clean the content and check length
    cleaned_content = clean_html_to_markdown(content).strip()
    if len(cleaned_content) < 20:
        return True, f"Article has minimal content (only {len(cleaned_content)} characters after cleaning)"
    
    # Check if it's just whitespace or basic HTML
    if not cleaned_content or cleaned_content.isspace():
        return True, "Article contains only whitespace after HTML cleaning"
    
    return False, ""

# Function to fetch data from Grab API
@st.cache_data
def fetch_grab_data(user_type, language_locale):
    """Fetch data from Grab help articles API"""
    url = f"https://help.grab.com/articles/v4/{user_type}/{language_locale}.json"
    
    try:
        response = requests.get(url, timeout=30)
        
        # Log the API call
        log_api_call(
            method="GET",
            url=url,
            status_code=response.status_code,
            success=response.status_code == 200,
            details=f"Fetch Grab articles for {user_type}/{language_locale}",
            response_data={"articles_count": len(response.json().get('articles', []))} if response.status_code == 200 else None
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

# Function to extract article data
def extract_articles(data):
    """Extract id, uuid, name, and body from articles"""
    if not data or 'articles' not in data:
        return []
    
    articles = []
    for article in data['articles']:
        # Clean the body content
        raw_body = article.get('body', '')
        cleaned_body = clean_html_to_markdown(raw_body)
        
        article_data = {
            'id': article.get('id'),
            'uuid': article.get('uuid'),
            'name': article.get('name'),
            'body': cleaned_body,
            'raw_body': raw_body  # Keep original for reference
        }
        articles.append(article_data)
    
    return articles

# Function to filter articles
def filter_articles(articles, filter_testing=True, filter_empty=True):
    """Filter out testing and/or empty articles and return production articles with analysis"""
    if not filter_testing and not filter_empty:
        return articles, [], []
    
    production_articles = []
    filtered_articles = []
    analysis_results = []
    
    for article in articles:
        is_test = False
        is_empty = False
        reasons = []
        
        # Check for testing
        if filter_testing:
            is_test, test_reason = is_testing_article(article)
            if is_test:
                reasons.append(f"Testing: {test_reason}")
        
        # Check for empty content
        if filter_empty:
            is_empty, empty_reason = is_empty_article(article)
            if is_empty:
                reasons.append(f"Empty: {empty_reason}")
        
        # Determine if article should be filtered
        should_filter = (filter_testing and is_test) or (filter_empty and is_empty)
        
        analysis_results.append({
            'id': article['id'],
            'name': article['name'],
            'is_filtered': should_filter,
            'is_testing': is_test,
            'is_empty': is_empty,
            'reasons': reasons,
            'article': article
        })
        
        if should_filter:
            filtered_articles.append(article)
        else:
            production_articles.append(article)
    
    return production_articles, filtered_articles, analysis_results

# Function to get articles from Ada knowledge source - UPDATED TO USE CORRECT ENDPOINT
def get_ada_articles(instance_name, api_key, knowledge_source_id=None):
    """Get all articles from Ada knowledge source using correct endpoint"""
    if not all([instance_name, api_key]):
        return False, "Missing configuration"
    
    # CORRECTED: Use the exact endpoint format from curl
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/articles/"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        all_articles = []
        page_count = 0
        
        while True:
            page_count += 1
            
            # Add pagination parameters
            params = {
                "page": page_count,
                "per_page": 100
            }
            
            # Add knowledge_source_id only if provided
            if knowledge_source_id:
                params["knowledge_source_id"] = knowledge_source_id
            
            response = requests.get(url, headers=headers, params=params)
            
            # Log each API call
            log_api_call(
                method="GET",
                url=f"{url}?{requests.models.PreparedRequest()._encode_params(params)}",
                status_code=response.status_code,
                success=response.status_code == 200,
                details=f"Get Ada articles page {page_count}" + (f" for knowledge source {knowledge_source_id}" if knowledge_source_id else " (all sources)"),
                response_data={"page": page_count, "articles_in_page": len(response.json().get('data', []))} if response.status_code == 200 else None
            )
            
            response.raise_for_status()
            result = response.json()
            
            # Check the response structure
            if 'data' in result and result['data']:
                # Filter by knowledge_source_id if specified (in case API doesn't filter)
                if knowledge_source_id:
                    filtered_articles = [
                        article for article in result['data']
                        if article.get('knowledge_source_id') == knowledge_source_id
                    ]
                    all_articles.extend(filtered_articles)
                else:
                    all_articles.extend(result['data'])
                
                # Check pagination metadata
                meta = result.get('meta', {})
                pagination = meta.get('pagination', {})
                
                # Check if there are more pages
                current_page = pagination.get('current_page', page_count)
                total_pages = pagination.get('total_pages', 1)
                
                if current_page >= total_pages:
                    break
                    
                # Alternative pagination check
                if len(result['data']) < 100:  # Less than full page means last page
                    break
                    
            else:
                # No data or empty response
                break
                
            # Safety break to prevent infinite loops
            if page_count > 100:  # Reasonable limit
                st.warning("Reached maximum page limit (100). There might be more articles.")
                break
        
        # Log final summary
        log_api_call(
            method="GET",
            url=url,
            status_code=200,
            success=True,
            details=f"Completed fetching Ada articles - {len(all_articles)} total articles from {page_count} pages" + (f" for source {knowledge_source_id}" if knowledge_source_id else "")
        )
        
        return True, {"data": all_articles, "total": len(all_articles)}
        
    except requests.exceptions.RequestException as e:
        error_detail = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
        
        log_api_call(
            method="GET",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error fetching Ada articles: {str(e)}. Details: {error_detail}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"



# Function to get articles with single endpoint - UPDATED
def get_ada_articles_robust(instance_name, api_key, knowledge_source_id):
    """Get articles from Ada using the correct endpoint with optional filtering"""
    
    st.info("🔍 Retrieving articles from Ada...")
    
    with st.spinner("Getting articles from Ada API..."):
        success, result = get_ada_articles(instance_name, api_key, knowledge_source_id)
        if success and result.get('total', 0) > 0:
            st.success(f"✅ Successfully retrieved {result['total']} articles")
            return success, result
        elif success:
            st.warning("⚠️ No articles found")
            return success, result
        else:
            st.error(f"❌ Failed to retrieve articles: {result}")
            return success, result

# Function to delete article from Ada - WITH LOGGING
def delete_ada_article(instance_name, api_key, article_id):
    """Delete a specific article from Ada"""
    if not all([instance_name, api_key, article_id]):
        return False, "Missing configuration"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/articles/{article_id}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.delete(url, headers=headers)
        
        # Log the API call
        log_api_call(
            method="DELETE",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 204],
            details=f"Delete Ada article {article_id}",
            response_data={"article_id": article_id}
        )
        
        response.raise_for_status()
        return True, "Article deleted successfully"
    except requests.exceptions.RequestException as e:
        error_detail = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
        
        log_api_call(
            method="DELETE",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error deleting Ada article {article_id}: {str(e)}. Details: {error_detail}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"

# Function to bulk delete articles
def bulk_delete_ada_articles(instance_name, api_key, article_ids):
    """Delete multiple articles from Ada with progress tracking"""
    if not all([instance_name, api_key]) or not article_ids:
        return False, "Missing configuration or no articles to delete"
    
    successful_deletions = []
    failed_deletions = []
    
    # Create progress tracking
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Log start of bulk operation
    log_api_call(
        method="DELETE",
        url="Bulk Delete Process",
        status_code=200,
        success=True,
        details=f"Starting bulk deletion of {len(article_ids)} articles"
    )
    
    for i, article_id in enumerate(article_ids):
        # Update progress
        progress = (i + 1) / len(article_ids)
        progress_bar.progress(progress)
        status_text.text(f"Deleting article {i+1} of {len(article_ids)}: {article_id}")
        
        success, result = delete_ada_article(instance_name, api_key, article_id)
        
        if success:
            successful_deletions.append(article_id)
        else:
            failed_deletions.append({"article_id": article_id, "error": result})
    
    # Clean up progress indicators
    progress_bar.empty()
    status_text.empty()
    
    # Log completion summary
    log_api_call(
        method="DELETE",
        url="Bulk Delete Complete",
        status_code=200,
        success=True,
        details=f"Completed bulk deletion: {len(successful_deletions)} successful, {len(failed_deletions)} failed",
        response_data={
            "successful": len(successful_deletions),
            "failed": len(failed_deletions),
            "total": len(article_ids)
        }
    )
    
    return True, {
        "successful": len(successful_deletions),
        "failed": len(failed_deletions),
        "successful_deletions": successful_deletions,
        "failed_deletions": failed_deletions,
        "total_processed": len(article_ids)
    }

# Function to compare articles step by step - CORRECTED
def compare_articles_detailed(grab_articles, ada_articles_data):
    """Compare Grab and Ada articles with detailed breakdown using correct ID matching"""
    
    # Step 1: Extract IDs from both sources
    grab_ids = set(str(article['id']) for article in grab_articles)
    grab_articles_dict = {str(article['id']): article for article in grab_articles}
    
    ada_articles = ada_articles_data.get('data', [])
    ada_ids = set()
    ada_articles_dict = {}
    
    for ada_article in ada_articles:
        # Use the article ID directly (not external_id)
        article_key = str(ada_article.get('id', ''))
        if article_key:
            ada_ids.add(article_key)
            ada_articles_dict[article_key] = ada_article
    
    # Step 2: Find differences
    # Articles in Ada but not in Grab (to be deleted)
    articles_to_delete = []
    for ada_id in ada_ids:
        if ada_id not in grab_ids:
            articles_to_delete.append(ada_articles_dict[ada_id])
    
    # Articles in Grab but not in Ada (to be added)
    articles_to_add = []
    for grab_id in grab_ids:
        if grab_id not in ada_ids:
            articles_to_add.append(grab_articles_dict[grab_id])
    
    # Articles in both (existing)
    articles_existing = []
    for grab_id in grab_ids:
        if grab_id in ada_ids:
            articles_existing.append({
                'grab_article': grab_articles_dict[grab_id],
                'ada_article': ada_articles_dict[grab_id]
            })
    
    # Log the comparison results
    log_api_call(
        method="COMPARE",
        url="Local Comparison",
        status_code=200,
        success=True,
        details=f"Article comparison completed",
        response_data={
            "grab_total": len(grab_articles),
            "ada_total": len(ada_articles),
            "to_delete": len(articles_to_delete),
            "to_add": len(articles_to_add),
            "existing": len(articles_existing)
        }
    )
    
    return {
        'articles_to_delete': articles_to_delete,
        'articles_to_add': articles_to_add,
        'articles_existing': articles_existing,
        'grab_total': len(grab_articles),
        'ada_total': len(ada_articles),
        'grab_ids': grab_ids,
        'ada_ids': ada_ids
    }

# Function to convert articles to Ada format - UPDATED WITH LANGUAGE AND NAME PREFIX OPTIONS
def convert_to_ada_format(articles, user_type, language_locale, knowledge_source_id, override_language=None, name_prefix=None):
    """Convert articles to Ada JSON format with correct structure including URL, language, and name prefix"""
    ada_articles = []
    
    # Determine the language to use
    language_to_use = override_language if override_language else language_locale
    
    for article in articles:
        # Generate the URL based on user type
        if user_type in ['moveitpassenger', 'moveitdriver']:
            # For MoveIt users, use moveit.com.ph domain and map user types
            if user_type == 'moveitpassenger':
                mapped_user_type = 'passenger'
            elif user_type == 'moveitdriver':
                mapped_user_type = 'driver'
            
            article_url = f"https://help.moveit.com.ph/{mapped_user_type}/{language_locale}/{article['id']}"
        else:
            # For regular Grab users, use grab.com domain
            article_url = f"https://help.grab.com/{user_type}/{language_locale}/{article['id']}"
        
        # Prepare the article name with optional prefix
        article_name = article['name'] or f"Article {article['id']}"
        if name_prefix:
            article_name = f"{name_prefix}{article_name}"
        
        # Use the Grab article ID as the Ada article ID
        ada_article = {
            "id": str(article['id']),  # Use article ID directly
            "name": article_name,  # Use 'name' not 'title' with optional prefix
            "content": article['body'] or "",  # Content in markdown format
            "knowledge_source_id": knowledge_source_id,  # Required field
            "url": article_url,  # Add URL field with correct domain
            "language": language_to_use  # Add language field
        }
        ada_articles.append(ada_article)
    
    return ada_articles

# Function to create individual article in Ada with real-time status - FIXED FOR BULK ENDPOINT
def create_ada_article_with_status(instance_name, api_key, article_data, status_container, index, total):
    """Create a single article in Ada using bulk endpoint - CORRECTED"""
    if not all([instance_name, api_key]):
        return False, "Missing configuration"
    
    # Update status
    article_name = article_data.get('name', 'Unknown')
    article_id = article_data.get('id', 'Unknown')
    
    with status_container.container():
        st.write(f"🔄 **Creating article {index}/{total}:** {article_name[:60]}{'...' if len(article_name) > 60 else ''}")
        st.write(f"📋 **Article ID:** `{article_id}`")
        st.write(f"🗂️ **Knowledge Source:** `{article_data.get('knowledge_source_id', 'Unknown')}`")
        st.write(f"🌐 **Language:** `{article_data.get('language', 'Unknown')}`")
        
        # Show a small progress indicator
        progress_text = st.empty()
        progress_text.write("⏳ Sending to bulk endpoint...")
    
    # CORRECTED: Use bulk endpoint as shown in curl example
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/bulk/articles/"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # IMPORTANT: Send as array (bulk format) even for single article
    payload = [article_data]
    
    try:
        start_time = time.time()
        
        with status_container.container():
            progress_text.write(f"📡 Sending POST request to bulk endpoint...")
        
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        end_time = time.time()
        
        # Update progress
        with status_container.container():
            progress_text.write(f"📡 Request completed in {end_time - start_time:.2f} seconds")
        
        # Log the API call
        log_api_call(
            method="POST",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 201],
            details=f"Create article '{article_data.get('name', 'Unknown')}' (ID: {article_data.get('id', 'Unknown')}) via bulk endpoint",
            response_data={
                "article_id": article_data.get('id'), 
                "article_name": article_data.get('name'),
                "language": article_data.get('language'),
                "endpoint_used": url,
                "response_data": response.json() if response.status_code in [200, 201] else None
            }
        )
        
        if response.status_code in [200, 201]:
            # Success
            with status_container.container():
                st.success(f"✅ **Successfully created:** {article_name}")
                st.write(f"📋 **Article ID:** `{article_id}`")
                st.write(f"🌐 **Language:** `{article_data.get('language', 'Unknown')}`")
                st.write(f"🌐 **Endpoint Used:** {url}")
                st.write(f"⏱️ **Response Time:** {end_time - start_time:.2f} seconds")
                st.write("---")
            return True, response.json()
        else:
            # API returned an error
            error_detail = ""
            try:
                error_detail = response.json()
            except:
                error_detail = response.text
            
            with status_container.container():
                st.error(f"❌ **Failed to create:** {article_name}")
                st.write(f"📋 **Article ID:** `{article_id}`")
                st.write(f"🌐 **Endpoint:** {url}")
                st.write(f"🚨 **Error Code:** {response.status_code}")
                st.write(f"📝 **Error Details:** {error_detail}")
                st.write("---")
            
            return False, f"HTTP {response.status_code}: {error_detail}"
            
    except requests.exceptions.Timeout:
        with status_container.container():
            st.error(f"⏰ **Timeout creating:** {article_name}")
            st.write(f"📋 **Article ID:** `{article_id}`")
            st.write("🚨 **Error:** Request timed out after 30 seconds")
            st.write("---")
        
        log_api_call(
            method="POST",
            url=url,
            status_code=0,
            success=False,
            details=f"Timeout creating article '{article_data.get('name', 'Unknown')}'"
        )
        
        return False, "Request timed out"
        
    except requests.exceptions.RequestException as e:
        error_detail = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
        
        with status_container.container():
            st.error(f"❌ **Network error creating:** {article_name}")
            st.write(f"📋 **Article ID:** `{article_id}`")
            st.write(f"🚨 **Error:** {str(e)}")
            if error_detail:
                st.write(f"📝 **Details:** {error_detail}")
            st.write("---")
        
        log_api_call(
            method="POST",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error creating article '{article_data.get('name', 'Unknown')}': {str(e)}. Details: {error_detail}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"

# Function to create articles individually with real-time status - ENHANCED WITH LANGUAGE AND NAME PREFIX
def create_articles_individually_with_status(articles, instance_name, knowledge_source_id, api_key, user_type, language_locale, override_language=None, name_prefix=None):
    """Create articles in Ada knowledge base with real-time status updates"""
    if not all([instance_name, knowledge_source_id, api_key]):
        return False, "Missing configuration"
    
    # Convert articles to Ada format with language and name prefix options
    ada_articles = convert_to_ada_format(articles, user_type, language_locale, knowledge_source_id, override_language, name_prefix)
    
    successful_uploads = []
    failed_uploads = []
    
    # Create main progress bar
    main_progress = st.progress(0)
    main_status = st.empty()
    
    # Create container for individual article status
    status_container = st.container()
    
    # Summary metrics containers
    metrics_container = st.container()
    
    # Log start of individual creation process
    log_api_call(
        method="POST",
        url="Individual Article Creation Process",
        status_code=200,
        success=True,
        details=f"Starting individual creation of {len(ada_articles)} articles with language: {override_language or language_locale}" + (f" and name prefix: '{name_prefix}'" if name_prefix else "")
    )
    
    # Initial metrics display
    with metrics_container:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            successful_metric = st.metric("✅ Successful", 0)
        with col2:
            failed_metric = st.metric("❌ Failed", 0)
        with col3:
            progress_metric = st.metric("📊 Progress", "0%")
        with col4:
            time_metric = st.metric("⏱️ Elapsed", "0s")
    
    start_time = time.time()
    
    for i, article_data in enumerate(ada_articles):
        # Update main progress
        progress = (i + 1) / len(ada_articles)
        main_progress.progress(progress)
        current_time = time.time()
        elapsed_time = current_time - start_time
        
        with main_status:
            st.write(f"🚀 **Processing article {i+1} of {len(ada_articles)}**")
        
        # Update metrics in real-time
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
        
        # Create individual article with status updates
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
        
        # Small delay to make the updates visible
        time.sleep(0.1)
    
    # Final cleanup
    main_progress.progress(1.0)
    total_time = time.time() - start_time
    
    # Final status update
    with main_status:
        st.write(f"🎉 **Upload process completed in {total_time:.1f} seconds!**")
    
    # Final metrics update
    with metrics_container:
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("✅ Successful", len(successful_uploads))
        with col2:
            st.metric("❌ Failed", len(failed_uploads))
        with col3:
            success_rate = (len(successful_uploads) / len(ada_articles)) * 100 if ada_articles else 0
            st.metric("📊 Success Rate", f"{success_rate:.1f}%")
        with col4:
            st.metric("⏱️ Total Time", f"{total_time:.1f}s")
    
    # Log completion summary
    log_api_call(
        method="POST",
        url="Individual Article Creation Complete",
        status_code=200,
        success=True,
        details=f"Completed individual article creation: {len(successful_uploads)} successful, {len(failed_uploads)} failed",
        response_data={
            "successful": len(successful_uploads),
            "failed": len(failed_uploads),
            "total": len(ada_articles),
            "total_time": total_time,
            "language_used": override_language or language_locale,
            "name_prefix_used": name_prefix
        }
    )
    
    # Return results
    return True, {
        "successful": len(successful_uploads),
        "failed": len(failed_uploads),
        "successful_uploads": successful_uploads,
        "failed_uploads": failed_uploads,
        "total_processed": len(ada_articles),
        "total_time": total_time
    }

# Function to create Ada knowledge source - UPDATED ID FORMAT
def create_ada_knowledge_source(instance_name, api_key, source_name, current_user_type, current_language_locale):
    """Create a new knowledge source in Ada"""
    if not all([instance_name, api_key, source_name]):
        return False, "Missing required fields"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    # Generate a simpler, Ada-compatible ID
    source_id = generate_source_id()
    
    # Correct payload structure - only id and name are allowed
    payload = {
        "id": source_id,
        "name": source_name
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload)
        
        # Log the API call
        log_api_call(
            method="POST",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 201],
            details=f"Create knowledge source '{source_name}' with ID '{source_id}'",
            response_data={"source_id": source_id, "source_name": source_name}
        )
        
        response.raise_for_status()
        result = response.json()
        
        # The source ID we provided should be in the response
        returned_source_id = result.get('data', {}).get('id', source_id)
        
        return True, {"source_id": returned_source_id, "response": result}
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
            details=f"Error creating knowledge source '{source_name}': {str(e)}. Details: {error_detail}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"

# Function to delete Ada knowledge source - WITH LOGGING
def delete_ada_knowledge_source(instance_name, api_key, source_id):
    """Delete a knowledge source from Ada"""
    if not all([instance_name, api_key, source_id]):
        return False, "Missing configuration"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources/{source_id}"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.delete(url, headers=headers)
        
        # Log the API call
        log_api_call(
            method="DELETE",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 204],
            details=f"Delete knowledge source {source_id}",
            response_data={"source_id": source_id}
        )
        
        response.raise_for_status()
        return True, "Knowledge source deleted successfully"
    except requests.exceptions.RequestException as e:
        error_detail = ""
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_detail = e.response.json()
            except:
                error_detail = e.response.text
        
        log_api_call(
            method="DELETE",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error deleting knowledge source {source_id}: {str(e)}. Details: {error_detail}"
        )
        
        return False, f"Error: {e}. Details: {error_detail}"

# Function to list Ada knowledge sources - WITH LOGGING
def list_ada_knowledge_sources(instance_name, api_key):
    """List all knowledge sources in Ada"""
    if not all([instance_name, api_key]):
        return False, "Missing required fields"
    
    url = f"https://{instance_name}.ada.support/api/v2/knowledge/sources"
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        
        # Log the API call
        log_api_call(
            method="GET",
            url=url,
            status_code=response.status_code,
            success=response.status_code == 200,
            details="List all knowledge sources",
            response_data={"sources_count": len(response.json().get('data', []))} if response.status_code == 200 else None
        )
        
        response.raise_for_status()
        return True, response.json()
    except requests.exceptions.RequestException as e:
        log_api_call(
            method="GET",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error listing knowledge sources: {str(e)}"
        )
        return False, f"Error: {e}"

# Sidebar for configuration
st.sidebar.header("Configuration")

# API Key Management Section
st.sidebar.subheader("🔐 API Key Management")

# Load existing configurations
saved_configs = list_saved_configs()

# Configuration selection
config_mode = st.sidebar.radio(
    "Configuration Mode:",
    ["Use Saved Config", "Enter Manually", "Save New Config"]
)

instance_name = ""
api_key = ""

if config_mode == "Use Saved Config":
    if saved_configs:
        # Create display options for selectbox
        config_options = [f"{config['name']} ({config['instance']})" for config in saved_configs]
        config_names = [config['name'] for config in saved_configs]
        
        selected_display = st.sidebar.selectbox(
            "Select Saved Configuration:",
            config_options
        )
        
        if selected_display:
            # Get the actual config name
            selected_index = config_options.index(selected_display)
            selected_config = config_names[selected_index]
            
            config_data = load_api_config(selected_config)
            if config_data:
                instance_name = config_data.get("instance_name", "")
                api_key = config_data.get("api_key", "")
                created_date = config_data.get("created_date", "Unknown")
                
                st.sidebar.success(f"✅ Loaded: {selected_config}")
                st.sidebar.write(f"**Instance:** {instance_name}")
                st.sidebar.write(f"**Created:** {created_date[:10]}")  # Show just the date
                
                # Store selected config in session state for deletion
                st.session_state.selected_config_for_deletion = selected_config
                
                # Test connection button
                if st.sidebar.button("🔄 Test Connection"):
                    with st.sidebar.spinner("Testing connection..."):
                        success, message = validate_ada_connection(instance_name, api_key)
                        if success:
                            st.sidebar.success(f"✅ {message}")
                        else:
                            st.sidebar.error(f"❌ {message}")
            else:
                st.sidebar.error("Failed to load configuration")
        
        # Delete configuration option
        if saved_configs and st.sidebar.button("🗑️ Delete Selected Config"):
            if hasattr(st.session_state, 'selected_config_for_deletion'):
                if delete_api_config(st.session_state.selected_config_for_deletion):
                    st.sidebar.success(f"Deleted: {st.session_state.selected_config_for_deletion}")
                    st.rerun()
                else:
                    st.sidebar.error("Failed to delete configuration")
        
        # Show all saved configs in an expandable section
        if saved_configs:
            with st.sidebar.expander("📋 All Saved Configs"):
                for config in saved_configs:
                    st.write(f"**{config['name']}**")
                    st.write(f"Instance: {config['instance']}")
                    st.write(f"Created: {config['created'][:10]}")
                    st.write("---")
    else:
        st.sidebar.info("No saved configurations found")
        st.sidebar.write("💡 Tip: Use 'Save New Config' to create your first configuration")

elif config_mode == "Enter Manually":
    instance_name = st.sidebar.text_input("Instance Name (without .ada.support):")
    api_key = st.sidebar.text_input("API Key:", type="password")
    
    # Test connection button for manual entry
    if instance_name and api_key and st.sidebar.button("🔄 Test Connection"):
        with st.sidebar.spinner("Testing connection..."):
            success, message = validate_ada_connection(instance_name, api_key)
            if success:
                st.sidebar.success(f"✅ {message}")
            else:
                st.sidebar.error(f"❌ {message}")

elif config_mode == "Save New Config":
    st.sidebar.write("Save a new API configuration for future use:")
    new_config_name = st.sidebar.text_input(
        "Configuration Name:",
        placeholder="e.g., 'Production', 'Staging', 'My Company'"
    )
    new_instance_name = st.sidebar.text_input(
        "Instance Name (without .ada.support):",
        placeholder="e.g., 'mycompany'"
    )
    new_api_key = st.sidebar.text_input(
        "API Key:", 
        type="password",
        placeholder="Your Ada API key"
    )
    
    # Test connection before saving
    if new_instance_name and new_api_key and st.sidebar.button("🔄 Test Connection Before Saving"):
        with st.sidebar.spinner("Testing connection..."):
            success, message = validate_ada_connection(new_instance_name, new_api_key)
            if success:
                st.sidebar.success(f"✅ {message}")
                st.session_state.connection_tested = True
            else:
                st.sidebar.error(f"❌ {message}")
                st.session_state.connection_tested = False
    
    if st.sidebar.button("💾 Save Configuration"):
        if all([new_config_name, new_instance_name, new_api_key]):
            # Check if config name already exists
            existing_names = [config['name'] for config in saved_configs]
            if new_config_name in existing_names:
                st.sidebar.error(f"Configuration '{new_config_name}' already exists!")
            else:
                if save_api_config(new_config_name, new_instance_name, new_api_key):
                    st.sidebar.success(f"✅ Saved: {new_config_name}")
                    st.sidebar.info("Switch to 'Use Saved Config' to use it")
                    # Clear the connection test state
                    if 'connection_tested' in st.session_state:
                        del st.session_state.connection_tested
                    st.rerun()
                else:
                    st.sidebar.error("Failed to save configuration")
        else:
            st.sidebar.error("Please fill in all fields")
    
    # Show example
    st.sidebar.write("📁 **Storage Location:**")
    st.sidebar.code(str(API_KEYS_DIR))

# Show current configuration status
if instance_name and api_key:
    st.sidebar.success("🟢 Ada API configured")
else:
    st.sidebar.warning("🟡 Ada API not configured")

# Parameters for Grab API
st.sidebar.subheader("Grab API Parameters")
user_type = st.sidebar.selectbox(
    "Select User Type:",
    ["passenger", "driver", "merchant", "moveitdriver", "moveitpassenger"]
)

language_locale = st.sidebar.text_input(
    "Language-Locale (e.g., en-ph):",
    value="en-ph"
)

# Article filtering options
st.sidebar.subheader("Article Filters")
filter_testing = st.sidebar.checkbox("Filter out testing articles", value=True)
filter_empty = st.sidebar.checkbox("Filter out empty articles", value=True)

if filter_testing:
    st.sidebar.write("Will exclude articles with test-related keywords")
if filter_empty:
    st.sidebar.write("Will exclude articles with no content")

# NEW: Ada Payload Options
st.sidebar.subheader("🔧 Ada Payload Options")

# Language Override Option
override_language_enabled = st.sidebar.checkbox(
    "Override Language Code", 
    value=False,
    help="Check this to use a different language code in the Ada payload than the one from Grab's JSON"
)

if override_language_enabled:
    override_language = st.sidebar.text_input(
        "Custom Language Code:",
        value=language_locale,
        placeholder="e.g., en-us, zh-cn, id-id",
        help="This will be used as the 'language' field in the Ada payload"
    )
else:
    override_language = None

# Name Prefix Option
name_prefix_enabled = st.sidebar.checkbox(
    "Add Name Prefix", 
    value=False,
    help="Check this to add a prefix to all article names in the Ada payload"
)

if name_prefix_enabled:
    name_prefix = st.sidebar.text_input(
        "Name Prefix:",
        value="",
        placeholder="e.g., 'Production - ', '[LIVE] ', 'Help: '",
        help="This text will be added to the beginning of each article name"
    )
    
    if name_prefix:
        st.sidebar.info(f"Example: '{name_prefix}How to book a ride'")
else:
    name_prefix = None

# Show the language configuration summary
st.sidebar.write("**Language Configuration:**")
if override_language_enabled and override_language:
    st.sidebar.write(f"🔄 Using custom language: `{override_language}`")
else:
    st.sidebar.write(f"📍 Using Grab's language: `{language_locale}`")

if name_prefix_enabled and name_prefix:
    st.sidebar.write(f"🏷️ Name prefix: `{name_prefix}`")

# Knowledge Source Management Section
st.header("🗂️ Ada Knowledge Source Management")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Create New Knowledge Source")
    new_source_name = st.text_input(
        "Knowledge Source Name:",
        placeholder=f"e.g., 'Grab {user_type.title()} Help - {language_locale.upper()}'"
    )
    
    if st.button("Create Knowledge Source", type="secondary"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings in the sidebar first")
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
                    st.write("Copy this Source ID to use in the article upload section below.")
                    
                    # Show the full response
                    with st.expander("View API Response"):
                        st.json(result['response'])
                        
                    # Store the new source ID for auto-population
                    st.session_state.selected_knowledge_source_id = result['source_id']
                    st.info("💡 This Source ID has been auto-selected for use below")
                else:
                    st.error(f"❌ Failed to create knowledge source:")
                    st.error(result)

with col2:
    st.subheader("List & Manage Knowledge Sources")
    
    if st.button("List Knowledge Sources", type="secondary"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings in the sidebar first")
        else:
            with st.spinner("Fetching knowledge sources..."):
                success, result = list_ada_knowledge_sources(instance_name, api_key)
                
                if success:
                    if 'data' in result and result['data']:
                        st.success(f"✅ Found {len(result['data'])} knowledge sources:")
                        
                        # Store knowledge sources in session state for later use
                        st.session_state.knowledge_sources = result['data']
                        
                        # Display as a nice table
                        sources_df = pd.DataFrame(result['data'])
                        if not sources_df.empty:
                            # Display the dataframe
                            st.dataframe(sources_df[['id', 'name']])
                            
                            # Add selection dropdown for easy copying
                            st.write("**Quick Select Knowledge Source:**")
                            source_options = [f"{source['name']} ({source['id']})" for source in result['data']]
                            selected_source_display = st.selectbox(
                                "Select a knowledge source to use:",
                                ["Select..."] + source_options,
                                key="knowledge_source_selector"
                            )
                            
                            if selected_source_display != "Select...":
                                # Extract the source ID from the selection
                                selected_source_id = selected_source_display.split("(")[-1].replace(")", "")
                                st.success(f"Selected Source ID: `{selected_source_id}`")
                                st.info("This ID will be auto-filled in the comparison section below")
                                
                                # Store selected source ID in session state
                                st.session_state.selected_knowledge_source_id = selected_source_id
                                
                                # Add delete option for selected source
                                st.write("**⚠️ Danger Zone: Delete Knowledge Source**")
                                if st.checkbox("I understand this will permanently delete the knowledge source and all its articles", key="confirm_delete"):
                                    if st.button("🗑️ Delete Selected Knowledge Source", type="primary", key="delete_source"):
                                        with st.spinner(f"Deleting knowledge source {selected_source_id}..."):
                                            delete_success, delete_result = delete_ada_knowledge_source(
                                                instance_name, api_key, selected_source_id
                                            )
                                            
                                            if delete_success:
                                                st.success("✅ Knowledge source deleted successfully!")
                                                # Clear the selected source from session state
                                                if 'selected_knowledge_source_id' in st.session_state:
                                                    del st.session_state.selected_knowledge_source_id
                                                st.rerun()
                                            else:
                                                st.error(f"❌ Failed to delete knowledge source: {delete_result}")
                        
                        # Also show as expandable JSON
                        with st.expander("View Raw JSON Response"):
                            st.json(result)
                    else:
                        st.info("No knowledge sources found")
                else:
                    st.error(f"❌ Failed to fetch knowledge sources: {result}")

st.divider()

# Article Retrieval Section
st.header("📥 Step 1: Retrieve Grab Articles")

current_url = f"https://help.grab.com/articles/v4/{user_type}/{language_locale}.json"
st.write(f"**API URL:** {current_url}")

if st.button("🔄 Fetch Articles from Grab", type="primary"):
    with st.spinner("Fetching articles from Grab..."):
        data = fetch_grab_data(user_type, language_locale)
        
        if data:
            all_articles = extract_articles(data)
            
            if all_articles:
                # Filter articles
                production_articles, filtered_articles, analysis = filter_articles(
                    all_articles, filter_testing, filter_empty
                )
                
                # Store in session state
                st.session_state.all_articles = all_articles
                st.session_state.production_articles = production_articles
                st.session_state.filtered_articles = filtered_articles
                st.session_state.analysis = analysis
                st.session_state.user_type = user_type
                st.session_state.language_locale = language_locale
                
                # Display results
                st.success(f"✅ **Successfully fetched {len(all_articles)} total articles**")
                
                # Show filtering results
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("📄 Total Articles", len(all_articles))
                with col2:
                    st.metric("✅ Production Articles", len(production_articles), 
                             delta=f"{len(production_articles)/len(all_articles)*100:.1f}%" if all_articles else "0%")
                with col3:
                    st.metric("🚫 Filtered Articles", len(filtered_articles),
                             delta=f"-{len(filtered_articles)/len(all_articles)*100:.1f}%" if all_articles else "0%")
                
                # Show detailed analysis with human-readable explanations
                if filtered_articles:
                    with st.expander(f"🚫 Filtered Articles ({len(filtered_articles)})", expanded=False):
                        for item in analysis:
                            if item['is_filtered']:
                                filter_type = "🧪" if item['is_testing'] else "📝" if item['is_empty'] else "❓"
                                st.warning(f"{filter_type} **Article ID {item['id']}:** {item['name']}")
                                for reason in item['reasons']:
                                    st.write(f"🔍 **Why filtered:** {reason}")
                                st.write("---")
                
                # Show content statistics
                st.subheader("Content Analysis")
                if production_articles:
                    articles_with_content = sum(1 for a in production_articles if len(a['body'].strip()) > 50)
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("📝 Rich Content", articles_with_content)
                    with col2:
                        st.metric("📄 Basic Content", len(production_articles) - articles_with_content)
                
                # Display sample data
                st.subheader("Production Articles Preview")
                if production_articles:
                    # Show cleaned content preview
                    preview_data = []
                    for article in production_articles[:5]:  # Show first 5
                        preview_data.append({
                            'ID': article['id'],
                            'Name': article['name'],
                            'Content Preview': article['body'][:100] + "..." if len(article['body']) > 100 else article['body'],
                            'Content Length': len(article['body'])
                        })
                    
                    preview_df = pd.DataFrame(preview_data)
                    st.dataframe(preview_df)
                    
                    # Show markdown conversion example
                    if st.checkbox("Show markdown conversion example"):
                        sample_article = production_articles[0]
                        col1, col2 = st.columns(2)
                        with col1:
                            st.subheader("Original HTML")
                            st.code(sample_article.get('raw_body', '')[:500] + "...")
                        with col2:
                            st.subheader("Converted Markdown")
                            st.markdown(sample_article['body'][:500] + "...")
                else:
                    st.warning("No production articles found after filtering")
                
            else:
                st.warning("No articles found in the response")
        else:
            st.error("Failed to fetch data. Please check your parameters.")

# Show fetched articles info
if 'production_articles' in st.session_state:
    articles_to_use = st.session_state.production_articles
    st.info(f"📋 {len(articles_to_use)} articles ready for download or upload to Ada")

st.divider()

# SECTION 2: Article Comparison and Cleanup Section (COLLAPSED)
with st.expander("🔄 Step 2: Advanced Article Comparison & Management", expanded=False):
    st.write("This section allows you to compare articles between Grab and Ada, and manage them.")
    
    # Auto-populate knowledge source ID if one was selected above
    default_comparison_id = ""
    if 'selected_knowledge_source_id' in st.session_state:
        default_comparison_id = st.session_state.selected_knowledge_source_id

    # Add UI for filtering options
    st.subheader("🔧 Article Retrieval Options")

    col1, col2 = st.columns(2)

    with col1:
        # Option to filter by knowledge source
        filter_by_source = st.checkbox("Filter by Knowledge Source", value=True, help="Check this to filter articles by a specific knowledge source. Uncheck to get all articles.")

    with col2:
        # Knowledge source ID input (only show if filtering is enabled)
        if filter_by_source:
            comparison_knowledge_source_id = st.text_input(
                "Knowledge Source ID:", 
                value=default_comparison_id,
                help="Enter the ID of the knowledge source to compare with Grab articles",
                key="comparison_source_id"
            )
        else:
            comparison_knowledge_source_id = None
            st.info("Will retrieve ALL articles from Ada (no filtering)")

    # Show helpful message if auto-populated
    if default_comparison_id and filter_by_source:
        st.info("💡 Knowledge Source ID auto-filled from your selection above")

    # Show the endpoint that will be used
    if filter_by_source and comparison_knowledge_source_id:
        st.code(f"GET https://{instance_name if instance_name else '{instance_name}'}.ada.support/api/v2/knowledge/articles/?knowledge_source_id={comparison_knowledge_source_id}")
    else:
        st.code(f"GET https://{instance_name if instance_name else '{instance_name}'}.ada.support/api/v2/knowledge/articles/")

    # STEP 1: Retrieve Articles from Ada
    st.subheader("📥 Step 2.1: Retrieve Articles from Ada")

    if st.button("🔍 Step 1: Get Articles from Ada Knowledge Source", type="secondary", key="comparison_step1"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings in the sidebar first")
        elif filter_by_source and not comparison_knowledge_source_id:
            st.error("Please enter a Knowledge Source ID or uncheck 'Filter by Knowledge Source'")
        elif 'all_articles' not in st.session_state:
            st.error("Please fetch articles from Grab first (Step 1)")
        else:
            with st.spinner("Retrieving articles from Ada knowledge base..."):
                # Get articles from Ada using robust method
                success, ada_result = get_ada_articles_robust(instance_name, api_key, comparison_knowledge_source_id)
                
                if success:
                    st.session_state.ada_articles_result = ada_result
                    st.session_state.comparison_source_id = comparison_knowledge_source_id
                    st.session_state.filter_by_source = filter_by_source
                    
                    # Display Ada articles summary
                    ada_count = len(ada_result.get('data', []))
                    
                    if filter_by_source and comparison_knowledge_source_id:
                        st.success(f"✅ Retrieved {ada_count} articles from knowledge source: {comparison_knowledge_source_id}")
                    else:
                        st.success(f"✅ Retrieved {ada_count} total articles from Ada")
                    
                    if ada_count > 0:
                        # Show preview of Ada articles
                        ada_articles = ada_result['data']
                        preview_data = []
                        for article in ada_articles[:5]:  # Show first 5
                            preview_data.append({
                                'Ada ID': article.get('id', 'N/A'),
                                'Name': article.get('name', 'No name'),
                                'Knowledge Source': article.get('knowledge_source_id', 'N/A'),
                                'Language': article.get('language', 'N/A'),  # NEW: Show language
                                'Content Length': len(article.get('content', ''))
                            })
                        
                        st.write("**Preview of Ada Articles:**")
                        preview_df = pd.DataFrame(preview_data)
                        st.dataframe(preview_df)
                        
                        st.info("✅ Ada articles retrieved successfully. Proceed to Step 2 for comparison.")
                    else:
                        if filter_by_source:
                            st.warning("Knowledge source is empty or doesn't exist. No articles to compare.")
                        else:
                            st.warning("No articles found in Ada. No articles to compare.")
                            
                else:
                    st.error(f"Failed to fetch articles from Ada: {ada_result}")

    # STEP 2: Compare Articles
    st.subheader("⚖️ Step 2.2: Compare Articles")

    if st.button("🔍 Step 2: Compare Grab vs Ada Articles", type="secondary", key="comparison_step2"):
        if 'ada_articles_result' not in st.session_state:
            st.error("Please complete Step 1 first (Get Articles from Ada)")
        elif 'all_articles' not in st.session_state:
            st.error("Please fetch articles from Grab first (main Step 1)")
        else:
            with st.spinner("Comparing articles..."):
                # Perform detailed comparison
                comparison_result = compare_articles_detailed(
                    st.session_state.all_articles, 
                    st.session_state.ada_articles_result
                )
                
                st.session_state.comparison_result = comparison_result
                
                # Display comparison results
                st.success("✅ Article comparison completed!")
                
                # Show summary metrics
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("📄 Grab Articles", comparison_result['grab_total'])
                with col2:
                    st.metric("📄 Ada Articles", comparison_result['ada_total'])
                with col3:
                    st.metric("🗑️ To Delete from Ada", len(comparison_result['articles_to_delete']))
                with col4:
                    st.metric("➕ To Add to Ada", len(comparison_result['articles_to_add']))
                
                # Show existing articles
                if comparison_result['articles_existing']:
                    st.info(f"✅ {len(comparison_result['articles_existing'])} articles exist in both Grab and Ada")
                
                # Show details
                if comparison_result['articles_to_delete'] or comparison_result['articles_to_add']:
                    st.info("📋 Detailed results available in Steps 3 and 4 below")
                else:
                    st.success("🎉 All articles are in sync! No actions needed.")

    # STEP 3: Delete Articles from Ada
    st.subheader("🗑️ Step 2.3: Delete Articles from Ada")

    if 'comparison_result' in st.session_state and st.session_state.comparison_result['articles_to_delete']:
        articles_to_delete = st.session_state.comparison_result['articles_to_delete']
        
        st.warning(f"Found {len(articles_to_delete)} articles in Ada that no longer exist in Grab")
        
        # Show articles to delete with selection
        st.write("**Articles to Delete from Ada:**")
        
        # Create selection interface
        delete_selections = {}
        delete_data = []
        
        for i, article in enumerate(articles_to_delete):
            article_id = article.get('id', 'Unknown')
            name = article.get('name', 'No name')
            
            # Create checkbox for each article
            delete_selections[article_id] = st.checkbox(
                f"Delete: {name} (ID: {article_id})",
                key=f"delete_{article_id}",
                value=False
            )
            
            delete_data.append({
                'Select': delete_selections[article_id],
                'Ada ID': article_id,
                'Name': name,
                'Knowledge Source': article.get('knowledge_source_id', 'N/A'),
                'Language': article.get('language', 'N/A')  # NEW: Show language
            })
        
        # Show table of articles to delete
        delete_df = pd.DataFrame(delete_data)
        st.dataframe(delete_df)
        
        # Bulk selection options
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Select All for Deletion", key="select_all_deletion"):
                for article_id in delete_selections.keys():
                    st.session_state[f"delete_{article_id}"] = True
                st.rerun()
        
        with col2:
            if st.button("Deselect All", key="deselect_all_deletion"):
                for article_id in delete_selections.keys():
                    st.session_state[f"delete_{article_id}"] = False
                st.rerun()
        
        # Delete selected articles
        selected_for_deletion = [
            article for article in articles_to_delete 
            if st.session_state.get(f"delete_{article.get('id')}", False)
        ]
        
        if selected_for_deletion:
            st.write(f"**{len(selected_for_deletion)} articles selected for deletion**")
            
            if st.checkbox("I understand this will permanently delete the selected articles from Ada", key="confirm_deletion"):
                if st.button("🗑️ Delete Selected Articles from Ada", type="primary", key="delete_articles"):
                    article_ids = [article.get('id') for article in selected_for_deletion]
                    
                    success, result = bulk_delete_ada_articles(instance_name, api_key, article_ids)
                    
                    if success:
                        # Show results
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("✅ Successful", result['successful'])
                        with col2:
                            st.metric("❌ Failed", result['failed'])
                        with col3:
                            success_rate = (result['successful'] / result['total_processed']) * 100 if result['total_processed'] > 0 else 0
                            st.metric("📊 Success Rate", f"{success_rate:.1f}%")
                        
                        if result['successful'] > 0:
                            st.success(f"✅ Successfully deleted {result['successful']} articles from Ada")
                        
                        if result['failed'] > 0:
                            with st.expander(f"Failed Deletions ({result['failed']})"):
                                for failed in result['failed_deletions']:
                                    st.error(f"Article ID: {failed['article_id']} - Error: {failed['error']}")
                        
                        # Refresh comparison after deletion
                        st.info("💡 Run the comparison again to see updated results")
                    else:
                        st.error(f"❌ Failed to delete articles: {result}")

    elif 'comparison_result' in st.session_state:
        st.success("✅ No articles need to be deleted from Ada")
    else:
        st.info("👆 Complete Step 2 (Compare Articles) to see articles that need deletion")

    # STEP 4: Add New Articles to Ada
    st.subheader("➕ Step 2.4: Add New Articles to Ada")

    if 'comparison_result' in st.session_state and st.session_state.comparison_result['articles_to_add']:
        articles_to_add = st.session_state.comparison_result['articles_to_add']
        
        st.info(f"Found {len(articles_to_add)} new articles in Grab that need to be added to Ada")
        
        # Show articles to add with selection
        st.write("**New Articles to Add to Ada:**")
        
        # Filter articles_to_add to only include production articles
        if 'production_articles' in st.session_state:
            production_ids = set(str(article['id']) for article in st.session_state.production_articles)
            articles_to_add_filtered = [
                article for article in articles_to_add 
                if str(article['id']) in production_ids
            ]
        else:
            articles_to_add_filtered = articles_to_add
        
        if len(articles_to_add_filtered) != len(articles_to_add):
            st.warning(f"Note: {len(articles_to_add) - len(articles_to_add_filtered)} articles were filtered out (testing/empty articles)")
        
        # Create selection interface
        add_selections = {}
        add_data = []
        
        for i, article in enumerate(articles_to_add_filtered):
            article_id = str(article.get('id', 'Unknown'))
            name = article.get('name', 'No name')
            content_length = len(article.get('body', ''))
            
            # Create checkbox for each article
            add_selections[article_id] = st.checkbox(
                f"Add: {name} ({content_length} chars)",
                key=f"add_{article_id}",
                value=True  # Default to selected
            )
            
            add_data.append({
                'Select': add_selections[article_id],
                'ID': article_id,
                'Name': name,
                'Content Length': content_length,
                'Content Preview': article.get('body', '')[:100] + "..." if len(article.get('body', '')) > 100 else article.get('body', '')
            })
        
        # Show table of articles to add
        if add_data:
            add_df = pd.DataFrame(add_data)
            st.dataframe(add_df)
            
            # Bulk selection options
            col1, col2 = st.columns(2)
            with col1:
                if st.button("Select All for Addition", key="select_all_addition"):
                    for article_id in add_selections.keys():
                        st.session_state[f"add_{article_id}"] = True
                    st.rerun()
            
            with col2:
                if st.button("Deselect All for Addition", key="deselect_all_addition"):
                    for article_id in add_selections.keys():
                        st.session_state[f"add_{article_id}"] = False
                    st.rerun()
            
            # Add selected articles
            selected_for_addition = [
                article for article in articles_to_add_filtered 
                if st.session_state.get(f"add_{str(article.get('id'))}", True)
            ]
            
            if selected_for_addition:
                st.write(f"**{len(selected_for_addition)} articles selected for addition to Ada**")
                
                # Preview what will be sent - UPDATED with correct URL pattern
                if st.checkbox("🔍 Preview articles that will be added to Ada", key="preview_addition"):
                    if selected_for_addition:
                        sample_ada_data = convert_to_ada_format(
                            selected_for_addition[:2], 
                            st.session_state.user_type, 
                            st.session_state.language_locale,
                            comparison_knowledge_source_id,
                            override_language,
                            name_prefix
                        )
                        st.write("**Preview of data format:**")
                        st.write(f"**Target Knowledge Source ID:** `{comparison_knowledge_source_id}`")
                        st.write(f"**Language:** `{override_language or st.session_state.language_locale}`")
                        if name_prefix:
                            st.write(f"**Name Prefix:** `{name_prefix}`")
                        
                        # Show correct URL pattern based on user type
                        if st.session_state.user_type in ['moveitpassenger', 'moveitdriver']:
                            mapped_type = 'passenger' if st.session_state.user_type == 'moveitpassenger' else 'driver'
                            st.write(f"**Sample URL Pattern:** `https://help.moveit.com.ph/{mapped_type}/{st.session_state.language_locale}/12345`")
                        else:
                            st.write(f"**Sample URL Pattern:** `https://help.grab.com/{st.session_state.user_type}/{st.session_state.language_locale}/12345`")
                        
                        st.json(sample_ada_data[0] if sample_ada_data else {})
                        if len(sample_ada_data) > 1:
                            st.write(f"... and {len(selected_for_addition)-1} more articles")
                
                if st.button("➕ Add Selected Articles to Ada", type="primary", key="add_articles_comparison"):
                    if not comparison_knowledge_source_id:
                        st.error("Please ensure Knowledge Source ID is provided")
                    else:
                        st.info("🚀 Starting real-time article upload process...")
                        
                        success, result = create_articles_individually_with_status(
                            selected_for_addition,
                            instance_name,
                            comparison_knowledge_source_id,
                            api_key,
                            st.session_state.user_type,
                            st.session_state.language_locale,
                            override_language,
                            name_prefix
                        )
                        
                        if success:
                            st.balloons()
                            
                            # Final summary
                            st.subheader("🎉 Upload Complete!")
                            
                            if result['successful'] > 0:
                                st.success(f"✅ Successfully uploaded {result['successful']} articles to Ada!")
                            
                            if result['failed'] > 0:
                                st.error(f"❌ {result['failed']} articles failed to upload")
                                
                                # Show failed articles summary
                                with st.expander(f"Failed Articles Details ({result['failed']})"):
                                    for failed in result['failed_uploads']:
                                        st.error(f"**{failed['article']['name']}**")
                                        st.write(f"ID: {failed['article']['id']}")
                                        st.write(f"Error: {failed['error']}")
                                        st.write("---")
                            
                            # Show successful articles summary - UPDATED with URL
                            if result['successful'] > 0:
                                with st.expander(f"Successful Articles Summary ({result['successful']})"):
                                    for successful in result['successful_uploads']:
                                        st.success(f"**{successful['article']['name']}**")
                                        st.write(f"Article ID: {successful['article']['id']}")
                                        st.write(f"Knowledge Source ID: {successful['article']['knowledge_source_id']}")
                                        st.write(f"Language: {successful['article']['language']}")
                                        st.write(f"URL: {successful['article']['url']}")
                                        st.write("---")
                            
                            # Refresh comparison after addition
                            st.info("💡 Run the comparison again to see updated results")
                        else:
                            st.error(f"❌ Failed to upload articles: {result}")
            else:
                st.info("No articles selected for addition")
        else:
            st.info("No new production articles to add")

    elif 'comparison_result' in st.session_state:
        st.success("✅ No new articles need to be added to Ada")
    else:
        st.info("👆 Complete Step 2 (Compare Articles) to see new articles that need to be added")

    # Summary Section
    if 'comparison_result' in st.session_state:
        st.subheader("📊 Comparison Summary")
        result = st.session_state.comparison_result
        
        col1, col2 = st.columns(2)
        with col1:
            st.write("**Grab Articles:**")
            st.write(f"- Total: {result['grab_total']}")
            st.write(f"- Unique IDs: {len(result['grab_ids'])}")
        
        with col2:
            st.write("**Ada Articles:**")
            st.write(f"- Total: {result['ada_total']}")
            st.write(f"- Unique IDs: {len(result['ada_ids'])}")
        
        st.write("**Sync Status:**")
        st.write(f"- ✅ In Sync: {len(result['articles_existing'])} articles")
        st.write(f"- 🗑️ To Delete: {len(result['articles_to_delete'])} articles")
        st.write(f"- ➕ To Add: {len(result['articles_to_add'])} articles")

st.divider()

# SECTION 3: Download Section (COLLAPSED)
with st.expander("📥 Step 3: Download Articles (Optional)", expanded=False):
    st.write("Download articles in various formats for backup or manual processing.")
    
    if 'production_articles' in st.session_state:
        # Choose which articles to download
        articles_to_download = st.session_state.production_articles
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("Download Original Format")
            
            # Original JSON format (with cleaned content)
            original_json = json.dumps(articles_to_download, indent=2)
            download_label = f"📄 Download {len(articles_to_download)} Articles as JSON"
            
            st.download_button(
                label=download_label,
                data=original_json,
                file_name=f"grab_articles_{st.session_state.user_type}_{st.session_state.language_locale}_cleaned.json",
                mime="application/json"
            )
        
        with col2:
            st.subheader("Download Ada Format")
            
            # Get knowledge source ID for download preview
            preview_knowledge_source_id = ""
            if 'selected_knowledge_source_id' in st.session_state:
                preview_knowledge_source_id = st.session_state.selected_knowledge_source_id
            elif 'comparison_source_id' in st.session_state:
                preview_knowledge_source_id = st.session_state.comparison_source_id
            else:
                preview_knowledge_source_id = "your-knowledge-source-id"
            
            # Ada format
            ada_format_data = convert_to_ada_format(
                articles_to_download, 
                st.session_state.user_type, 
                st.session_state.language_locale,
                preview_knowledge_source_id,
                override_language,
                name_prefix
            )
            ada_json = json.dumps(ada_format_data, indent=2)
            
            ada_download_label = f"🔄 Download {len(articles_to_download)} Articles for Ada"
            
            st.download_button(
                label=ada_download_label,
                data=ada_json,
                file_name=f"ada_articles_{st.session_state.user_type}_{st.session_state.language_locale}_ready.json",
                mime="application/json"
            )
            
            # Preview Ada format with knowledge source ID and URL visible
            if st.checkbox("Preview Ada format", key="download_preview"):
                if ada_format_data:
                    st.write("**Sample Ada format:**")
                    st.write(f"**Knowledge Source ID:** `{preview_knowledge_source_id}`")
                    st.write(f"**Language:** `{override_language or st.session_state.language_locale}`")
                    if name_prefix:
                        st.write(f"**Name Prefix:** `{name_prefix}`")
                    
                    # Show correct URL pattern based on user type
                    if st.session_state.user_type in ['moveitpassenger', 'moveitdriver']:
                        mapped_type = 'passenger' if st.session_state.user_type == 'moveitpassenger' else 'driver'
                        st.write(f"**URL Pattern:** `https://help.moveit.com.ph/{mapped_type}/{st.session_state.language_locale}/12345`")
                    else:
                        st.write(f"**URL Pattern:** `https://help.grab.com/{st.session_state.user_type}/{st.session_state.language_locale}/12345`")
                    
                    sample_article = ada_format_data[0]
                    st.json(sample_article)

        # Option to download filtered articles separately
        if 'filtered_articles' in st.session_state and st.session_state.filtered_articles:
            st.subheader("Download Filtered Articles (Optional)")
            st.write(f"Found {len(st.session_state.filtered_articles)} filtered articles")
            
            filtered_json = json.dumps(st.session_state.filtered_articles, indent=2)
            st.download_button(
                label=f"🚫 Download {len(st.session_state.filtered_articles)} Filtered Articles",
                data=filtered_json,
                file_name=f"grab_filtered_articles_{st.session_state.user_type}_{st.session_state.language_locale}.json",
                mime="application/json"
            )

    else:
        st.info("👆 Please fetch articles first to enable download options")

st.divider()

# Upload to Ada Section - INDIVIDUAL ONLY WITH REAL-TIME STATUS
st.header("📤 Step 4: Upload Articles to Ada")

if 'production_articles' in st.session_state:
    articles_to_upload = st.session_state.production_articles
    
    st.write(f"**Ready to upload {len(articles_to_upload)} articles to Ada**")
    if 'filtered_articles' in st.session_state:
        st.info(f"ℹ️ {len(st.session_state.filtered_articles)} articles will be excluded from upload")
    
    # Auto-populate knowledge source ID if one was selected above
    default_upload_id = ""
    if 'selected_knowledge_source_id' in st.session_state:
        default_upload_id = st.session_state.selected_knowledge_source_id
    
    # Knowledge source selection
    knowledge_source_id = st.text_input(
        "Knowledge Source ID:", 
        value=default_upload_id,
        help="Enter the ID of the knowledge source where articles will be uploaded, or select one from 'List Knowledge Sources' above",
        key="upload_knowledge_source_id"
    )
    
    # Show helpful message if auto-populated
    if default_upload_id:
        st.info("💡 Knowledge Source ID auto-filled from your selection above")
    
    # Show current configuration summary
    st.subheader("🔧 Upload Configuration")
    col1, col2 = st.columns(2)
    
    with col1:
        st.write("**Language Settings:**")
        if override_language_enabled and override_language:
            st.write(f"🔄 Custom language: `{override_language}`")
        else:
            st.write(f"📍 Grab's language: `{language_locale}`")
    
    with col2:
        st.write("**Name Settings:**")
        if name_prefix_enabled and name_prefix:
            st.write(f"🏷️ Prefix: `{name_prefix}`")
            st.write(f"Example: `{name_prefix}How to book a ride`")
        else:
            st.write("📝 No prefix (original names)")
    
    # Preview what will be sent - UPDATED with correct URL pattern
    if st.checkbox("🔍 Preview data that will be sent to Ada"):
        if articles_to_upload and knowledge_source_id:
            sample_ada_data = convert_to_ada_format(
                articles_to_upload[:2], 
                st.session_state.user_type, 
                st.session_state.language_locale,
                knowledge_source_id,
                override_language,
                name_prefix
            )
            st.write("**Preview of data that will be sent to Ada:**")
            st.write(f"**Target Knowledge Source ID:** `{knowledge_source_id}`")
            st.write(f"**Total Articles to Upload:** {len(articles_to_upload)}")
            st.write(f"**Language:** `{override_language or language_locale}`")
            if name_prefix:
                st.write(f"**Name Prefix:** `{name_prefix}`")
            
            # Show correct URL pattern based on user type
            if st.session_state.user_type in ['moveitpassenger', 'moveitdriver']:
                mapped_type = 'passenger' if st.session_state.user_type == 'moveitpassenger' else 'driver'
                st.write(f"**URL Pattern:** `https://help.moveit.com.ph/{mapped_type}/{st.session_state.language_locale}/12345`")
            else:
                st.write(f"**URL Pattern:** `https://help.grab.com/{st.session_state.user_type}/{st.session_state.language_locale}/12345`")
            
            if sample_ada_data:
                st.write("**Sample Article Structure:**")
                st.json(sample_ada_data[0])
                if len(sample_ada_data) > 1:
                    st.write(f"... and {len(articles_to_upload)-1} more articles with the same structure")
                
                # Show a summary table - with URL column
                preview_summary = []
                for i, article in enumerate(sample_ada_data):
                    preview_summary.append({
                        'Article ID': article['id'],
                        'Name': article['name'][:50] + "..." if len(article['name']) > 50 else article['name'],
                        'Content Length': len(article['content']),
                        'Knowledge Source ID': article['knowledge_source_id'],
                        'Language': article['language'],
                        'URL': article['url']
                    })
                
                st.write("**Preview Summary:**")
                preview_df = pd.DataFrame(preview_summary)
                st.dataframe(preview_df)
        elif not knowledge_source_id:
            st.warning("Please enter Knowledge Source ID to see preview")
    
    # Upload button - Individual only with real-time status
    st.subheader("🚀 Individual Upload with Real-Time Status")
    st.write("Watch each article being created in real-time with detailed status updates.")
    
    if st.button("📤 Start Individual Upload with Live Status", type="primary"):
        if not all([instance_name, api_key]):
            st.error("Please configure Ada API settings in the sidebar first")
        elif not knowledge_source_id:
            st.error("Please enter a Knowledge Source ID or select one from 'List Knowledge Sources' above")
        else:
            st.header("🔄 Real-Time Upload Progress")
            st.write(f"Uploading {len(articles_to_upload)} articles to Knowledge Source: `{knowledge_source_id}`")
            if override_language:
                st.write(f"Using custom language: `{override_language}`")
            if name_prefix:
                st.write(f"Using name prefix: `{name_prefix}`")
            st.write("---")
            
            success, result = create_articles_individually_with_status(
                articles_to_upload, 
                instance_name, 
                knowledge_source_id, 
                api_key,
                st.session_state.user_type,
                st.session_state.language_locale,
                override_language,
                name_prefix
            )
            
            if success:
                st.balloons()
                
                # Final comprehensive summary
                st.header("🎉 Upload Process Complete!")
                
                # Overall metrics
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
                
                # Configuration summary
                st.write("**Upload Configuration Used:**")
                st.write(f"- Language: `{override_language or language_locale}`")
                if name_prefix:
                    st.write(f"- Name Prefix: `{name_prefix}`")
                st.write(f"- Knowledge Source: `{knowledge_source_id}`")
                
                # Detailed results
                if result['successful'] > 0:
                    st.success(f"✅ Successfully uploaded {result['successful']} articles to Ada!")
                    
                    with st.expander(f"📋 Successful Articles Details ({result['successful']})"):
                        success_data = []
                        for successful in result['successful_uploads']:
                            success_data.append({
                                'Article ID': successful['article']['id'],
                                'Name': successful['article']['name'],
                                'Knowledge Source ID': successful['article']['knowledge_source_id'],
                                'Language': successful['article']['language'],
                                'Content Length': len(successful['article']['content']),
                                'URL': successful['article']['url']
                            })
                        
                        if success_data:
                            success_df = pd.DataFrame(success_data)
                            st.dataframe(success_df)
                
                if result['failed'] > 0:
                    st.error(f"❌ {result['failed']} articles failed to upload")
                    
                    with st.expander(f"🚨 Failed Articles Details ({result['failed']})"):
                        for failed in result['failed_uploads']:
                            st.error(f"**{failed['article']['name']}**")
                            st.write(f"Article ID: {failed['article']['id']}")
                            st.write(f"Error: {failed['error']}")
                            st.write("---")
                
                # Next steps
                st.info("💡 **Next Steps:**")
                st.write("- Use the comparison tool in Step 2 to verify all articles were uploaded correctly")
                st.write("- Check the API call log below for detailed operation history")
                
            else:
                st.error(f"❌ Failed to upload articles: {result}")

else:
    st.info("👆 Please fetch articles first before uploading to Ada")

st.divider()

# API Call Log Section (COMPLETED)
st.header("📋 API Call Log")

if st.session_state.api_call_log:
    # Controls for the log
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        show_successful = st.checkbox("Show Successful Calls", value=True)
    with col2:
        show_failed = st.checkbox("Show Failed Calls", value=True)
    with col3:
        if st.button("🗑️ Clear Log"):
            clear_api_log()
            st.success("API log cleared!")
            st.rerun()
    with col4:
        # Export log button
        log_json = export_api_log()
        if log_json:
            st.download_button(
                label="📄 Export Log",
                data=log_json,
                file_name=f"api_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json"
            )
    
    # Filter logs based on user selection
    filtered_logs = []
    for log_entry in st.session_state.api_call_log:
        if (show_successful and log_entry['success']) or (show_failed and not log_entry['success']):
            filtered_logs.append(log_entry)
    
    if filtered_logs:
        # Summary metrics
        successful_calls = sum(1 for log in filtered_logs if log['success'])
        failed_calls = sum(1 for log in filtered_logs if not log['success'])
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Calls", len(filtered_logs))
        with col2:
            st.metric("✅ Successful", successful_calls)
        with col3:
            st.metric("❌ Failed", failed_calls)
        
        # Display logs
        st.subheader("API Call Details")
        
        for i, log_entry in enumerate(reversed(filtered_logs[-20:])):  # Show last 20 calls
            # Color coding based on success
            if log_entry['success']:
                status_color = "🟢"
                container = st.container()
            else:
                status_color = "🔴"
                container = st.container()
            
            with container:
                col1, col2, col3, col4 = st.columns([1, 2, 1, 2])
                
                with col1:
                    st.write(f"{status_color} **{log_entry['method']}**")
                
                with col2:
                    # Truncate long URLs
                    display_url = log_entry['url']
                    if len(display_url) > 50:
                        display_url = display_url[:47] + "..."
                    st.write(f"`{display_url}`")
                
                with col3:
                    st.write(f"**{log_entry['status_code']}**")
                
                with col4:
                    st.write(log_entry['timestamp'])
                
                # Details
                if log_entry['details']:
                    st.write(f"📝 {log_entry['details']}")
                
                # Response data (if available)
                if log_entry.get('response_data'):
                    with st.expander(f"Response Data (Call #{len(filtered_logs)-i})"):
                        st.json(log_entry['response_data'])
                
                st.divider()
        
        # Show more logs option
        if len(filtered_logs) > 20:
            st.info(f"Showing last 20 calls. Total: {len(filtered_logs)} calls in log.")
            
            with st.expander("Show All Logs"):
                for log_entry in filtered_logs:
                    st.write(f"{log_entry['timestamp']} | {log_entry['method']} | {log_entry['url']} | {log_entry['status_code']} | {log_entry['details']}")
    
    else:
        st.info("No API calls match your filter criteria.")

else:
    st.info("No API calls logged yet. Start by fetching articles or managing knowledge sources.")

# Additional Features Section
st.divider()
st.header("🛠️ Additional Features")

# Quick Actions
col1, col2 = st.columns(2)

with col1:
    st.subheader("🔧 Quick Actions")
    
    # Clear all session data
    if st.button("🧹 Clear All Session Data"):
        # Clear all session state except API log
        keys_to_keep = ['api_call_log']
        keys_to_remove = [key for key in st.session_state.keys() if key not in keys_to_keep]
        for key in keys_to_remove:
            del st.session_state[key]
        st.success("✅ Session data cleared!")
        st.rerun()
    
    # Show session state info
    if st.checkbox("Show Session State Info"):
        st.write("**Current Session Data:**")
        session_info = {}
        for key, value in st.session_state.items():
            if key != 'api_call_log':  # Don't show full log
                if isinstance(value, list):
                    session_info[key] = f"List with {len(value)} items"
                elif isinstance(value, dict):
                    session_info[key] = f"Dict with {len(value)} keys"
                else:
                    session_info[key] = str(type(value).__name__)
        
        st.json(session_info)

with col2:
    st.subheader("📊 Statistics")
    
    if 'api_call_log' in st.session_state and st.session_state.api_call_log:
        total_calls = len(st.session_state.api_call_log)
        successful_calls = sum(1 for log in st.session_state.api_call_log if log['success'])
        failed_calls = total_calls - successful_calls
        
        # API call statistics
        st.metric("Total API Calls", total_calls)
        col1_stat, col2_stat = st.columns(2)
        with col1_stat:
            st.metric("Successful", successful_calls)
        with col2_stat:
            st.metric("Failed", failed_calls)
        
        # Success rate
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
        st.metric("Success Rate", f"{success_rate:.1f}%")
    
    # Session statistics
    if 'all_articles' in st.session_state:
        st.write("**Article Statistics:**")
        st.write(f"- Total Fetched: {len(st.session_state.all_articles)}")
        if 'production_articles' in st.session_state:
            st.write(f"- Production: {len(st.session_state.production_articles)}")
        if 'filtered_articles' in st.session_state:
            st.write(f"- Filtered: {len(st.session_state.filtered_articles)}")

# Footer
st.divider()
st.markdown("---")
col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("**Grab to Ada Knowledge Base Manager**")
    st.markdown("Built with ❤️ using Streamlit")

with col2:
    st.markdown("**Key Features:**")
    st.markdown("• Real-time upload status")
    st.markdown("• Individual article tracking")
    st.markdown("• Language override options")
    st.markdown("• Name prefix customization")
    st.markdown("• Comprehensive error handling")
    st.markdown("• Knowledge source management")

with col3:
    st.markdown("**Best Practices:**")
    st.markdown("💡 Monitor real-time status")
    st.markdown("🔄 Test connections first")
    st.markdown("📋 Review previews before upload")
    st.markdown("🌐 Check language settings")
    st.markdown("🏷️ Use name prefixes for organization")
    st.markdown("📊 Check logs for troubleshooting")

# Version info
st.markdown("---")
st.markdown("*Version 3.1 - Enhanced with language override and name prefix options, improved UI organization*")
