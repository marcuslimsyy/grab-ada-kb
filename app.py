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

def is_testing_article(article):
    """Detect if an article is a testing article"""
    test_keywords = [
        'test', 'testing', 'qa', 'quality assurance', 'dummy', 'sample',
        'lorem ipsum', 'placeholder', 'debug', 'dev', 'development',
        'staging', 'temp', 'temporary', 'draft', 'wip', 'work in progress',
        'do not publish', 'internal', 'beta', 'alpha', 'experiment',
        'trial', 'demo', 'example', 'mock', 'fake', 'zzz', 'xxx',
        'asdf', 'qwerty', '123test', 'test123', 'testtest'
    ]
    
    article_id = str(article.get('id', ''))
    article_name = str(article.get('name', '')).lower()
    article_body = str(article.get('body', '')).lower()
    
    # Check keywords in title
    for keyword in test_keywords:
        if keyword in article_name:
            return True, f"Contains test-related word '{keyword}' in the title"
    
    # Check keywords in body
    body_preview = article_body[:200]
    for keyword in test_keywords:
        if keyword in body_preview:
            return True, f"Contains test-related word '{keyword}' in the article content"
    
    # Check ID patterns
    if re.search(r'test\d+', article_id, re.IGNORECASE):
        return True, "Article ID follows test pattern"
    
    # Check content length
    if len(article_body.strip()) < 10:
        return True, "Article has very little content"
    
    return False, ""

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
            'raw_body': raw_body
        }
        articles.append(article_data)
    
    return articles

def filter_articles(articles, filter_testing=True, filter_empty=True):
    """Filter out testing and/or empty articles"""
    if not filter_testing and not filter_empty:
        return articles, [], []
    
    production_articles = []
    filtered_articles = []
    analysis_results = []
    
    for article in articles:
        is_test = False
        is_empty = False
        reasons = []
        
        if filter_testing:
            is_test, test_reason = is_testing_article(article)
            if is_test:
                reasons.append(f"Testing: {test_reason}")
        
        if filter_empty:
            is_empty, empty_reason = is_empty_article(article)
            if is_empty:
                reasons.append(f"Empty: {empty_reason}")
        
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

def convert_to_ada_format(articles, user_type, language_locale, knowledge_source_id, override_language=None, name_prefix=None, id_prefix=None):
    """Convert articles to Ada JSON format"""
    ada_articles = []
    
    language_to_use = override_language if override_language else language_locale
    
    for article in articles:
        # Generate URL based on user type
        if user_type in ['moveitpassenger', 'moveitdriver']:
            if user_type == 'moveitpassenger':
                mapped_user_type = 'passenger'
            elif user_type == 'moveitdriver':
                mapped_user_type = 'driver'
            
            article_url = f"https://help.moveit.com.ph/{mapped_user_type}/{language_locale}/{article['id']}"
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
        
        ada_article = {
            "id": article_id,
            "name": article_name,
            "content": article['body'] or "",
            "knowledge_source_id": knowledge_source_id,
            "url": article_url,
            "language": language_to_use
        }
        ada_articles.append(ada_article)
    
    return ada_articles

def create_ada_article_with_status(instance_name, api_key, article_data, status_container, index, total):
    """Create a single article in Ada using bulk endpoint"""
    if not all([instance_name, api_key]):
        return False, "Missing configuration"
    
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
    
    try:
        start_time = time.time()
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        end_time = time.time()
        
        log_api_call(
            method="POST",
            url=url,
            status_code=response.status_code,
            success=response.status_code in [200, 201],
            details=f"Create article '{article_data.get('name', 'Unknown')}' (ID: {article_data.get('id', 'Unknown')})"
        )
        
        if response.status_code in [200, 201]:
            with status_container.container():
                st.success(f"✅ **Successfully created:** {article_name}")
                st.write(f"⏱️ **Response Time:** {end_time - start_time:.2f} seconds")
                st.write("---")
            return True, response.json()
        else:
            error_detail = ""
            try:
                error_detail = response.json()
            except:
                error_detail = response.text
            
            with status_container.container():
                st.error(f"❌ **Failed to create:** {article_name}")
                st.write(f"🚨 **Error Code:** {response.status_code}")
                st.write(f"📝 **Error Details:** {error_detail}")
                st.write("---")
            
            return False, f"HTTP {response.status_code}: {error_detail}"
            
    except requests.exceptions.Timeout:
        with status_container.container():
            st.error(f"⏰ **Timeout creating:** {article_name}")
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
        with status_container.container():
            st.error(f"❌ **Network error creating:** {article_name}")
            st.write(f"🚨 **Error:** {str(e)}")
            st.write("---")
        
        log_api_call(
            method="POST",
            url=url,
            status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
            success=False,
            details=f"Error creating article '{article_data.get('name', 'Unknown')}': {str(e)}"
        )
        
        return False, f"Error: {e}"

def create_articles_individually_with_status(articles, instance_name, knowledge_source_id, api_key, user_type, language_locale, override_language=None, name_prefix=None, id_prefix=None):
    """Create articles in Ada knowledge base with real-time status updates"""
    if not all([instance_name, knowledge_source_id, api_key]):
        return False, "Missing configuration"
    
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
        
        time.sleep(0.1)
    
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

# API Key Management
st.sidebar.subheader("🔐 API Key Management")
saved_configs = list_saved_configs()

config_mode = st.sidebar.radio(
    "Configuration Mode:",
    ["Use Saved Config", "Enter Manually", "Save New Config"]
)

instance_name = ""
api_key = ""

if config_mode == "Use Saved Config":
    if saved_configs:
        config_options = [f"{config['name']} ({config['instance']})" for config in saved_configs]
        config_names = [config['name'] for config in saved_configs]
        
        selected_display = st.sidebar.selectbox(
            "Select Saved Configuration:",
            config_options
        )
        
        if selected_display:
            selected_index = config_options.index(selected_display)
            selected_config = config_names[selected_index]
            
            config_data = load_api_config(selected_config)
            if config_data:
                instance_name = config_data.get("instance_name", "")
                api_key = config_data.get("api_key", "")
                
                st.sidebar.success(f"✅ Loaded: {selected_config}")
                st.sidebar.write(f"**Instance:** {instance_name}")
                
                if st.sidebar.button("🔄 Test Connection"):
                    with st.sidebar.spinner("Testing connection..."):
                        success, message = validate_ada_connection(instance_name, api_key)
                        if success:
                            st.sidebar.success(f"✅ {message}")
                        else:
                            st.sidebar.error(f"❌ {message}")
        
        if saved_configs and st.sidebar.button("🗑️ Delete Selected Config"):
            if delete_api_config(selected_config):
                st.sidebar.success(f"Deleted: {selected_config}")
                st.rerun()
    else:
        st.sidebar.info("No saved configurations found")

elif config_mode == "Enter Manually":
    instance_name = st.sidebar.text_input("Instance Name (without .ada.support):")
    api_key = st.sidebar.text_input("API Key:", type="password")
    
    if instance_name and api_key and st.sidebar.button("🔄 Test Connection"):
        with st.sidebar.spinner("Testing connection..."):
            success, message = validate_ada_connection(instance_name, api_key)
            if success:
                st.sidebar.success(f"✅ {message}")
            else:
                st.sidebar.error(f"❌ {message}")

elif config_mode == "Save New Config":
    new_config_name = st.sidebar.text_input("Configuration Name:")
    new_instance_name = st.sidebar.text_input("Instance Name (without .ada.support):")
    new_api_key = st.sidebar.text_input("API Key:", type="password")
    
    if st.sidebar.button("💾 Save Configuration"):
        if all([new_config_name, new_instance_name, new_api_key]):
            existing_names = [config['name'] for config in saved_configs]
            if new_config_name in existing_names:
                st.sidebar.error(f"Configuration '{new_config_name}' already exists!")
            else:
                if save_api_config(new_config_name, new_instance_name, new_api_key):
                    st.sidebar.success(f"✅ Saved: {new_config_name}")
                    st.rerun()
        else:
            st.sidebar.error("Please fill in all fields")

# Show current configuration status
if instance_name and api_key:
    st.sidebar.success("🟢 Ada API configured")
else:
    st.sidebar.warning("🟡 Ada API not configured")

# Grab API Parameters
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

current_url = f"https://help.grab.com/articles/v4/{user_type}/{language_locale}.json"
st.write(f"**API URL:** {current_url}")

if st.button("🔄 Fetch Articles from Grab", type="primary"):
    with st.spinner("Fetching articles from Grab..."):
        data = fetch_grab_data(user_type, language_locale)
        
        if data:
            all_articles = extract_articles(data)
            
            if all_articles:
                production_articles, filtered_articles, analysis = filter_articles(
                    all_articles, filter_testing, filter_empty
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
    st.info(f"📋 {len(articles_to_use)} articles ready for upload to Ada")

st.divider()

# Upload to Ada
st.header("📤 Upload Articles to Ada")

if 'production_articles' in st.session_state:
    articles_to_upload = st.session_state.production_articles
    
    st.write(f"**Ready to upload {len(articles_to_upload)} articles to Ada**")
    
    # Auto-populate knowledge source ID
    default_upload_id = ""
    if 'selected_knowledge_source_id' in st.session_state:
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
                        'URL': article['url']
                    })
                
                preview_df = pd.DataFrame(preview_summary)
                st.dataframe(preview_df)
    
    # Upload button
    if st.button("📤 Start Upload with Live Status", type="primary"):
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
    st.markdown("**Key Features:**")
    st.markdown("• Real-time upload status")
    st.markdown("• Language override options")
    st.markdown("• Name & ID prefix customization")
    st.markdown("• Knowledge source management")
    st.markdown("• Comprehensive error handling")

st.markdown("---")
st.markdown("*Version 3.2 - Clean UI with ID prefix functionality*")
