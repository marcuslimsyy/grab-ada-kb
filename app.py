# Article Comparison Section
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
            has_more = True
            total_fetched = 0
            
            with fetch_container:
                st.subheader("📡 Fetching Ada Articles")
                page_status = st.empty()
                articles_status = st.empty()
            
            while has_more:
                url = f"https://{instance_name}.ada.support/api/v2/knowledge/articles/"
                headers = {
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json"
                }
                
                params = {
                    "knowledge_source_id": comparison_knowledge_source_id,
                    "page": page
                }
                
                with page_status:
                    st.write(f"🔄 **Fetching page {page}...**")
                
                try:
                    start_time = time.time()
                    response = requests.get(url, headers=headers, params=params, timeout=30)
                    end_time = time.time()
                    
                    log_api_call(
                        method="GET",
                        url=f"{url}?knowledge_source_id={comparison_knowledge_source_id}&page={page}",
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
                    
                    if not articles:
                        has_more = False
                        with page_status:
                            st.info("✅ **No more articles found - fetch complete**")
                    else:
                        all_ada_articles.extend(articles)
                        total_fetched += len(articles)
                        page += 1
                        
                        with page_status:
                            st.success(f"✅ **Page {page-1} fetched:** {len(articles)} articles ({end_time - start_time:.2f}s)")
                        
                        with articles_status:
                            st.metric("📊 Total Articles Fetched", total_fetched)
                    
                    # Check if there's pagination info
                    meta = data.get('meta', {})
                    if 'has_next' in meta:
                        has_more = meta['has_next']
                    elif len(articles) == 0:
                        has_more = False
                        
                except requests.exceptions.RequestException as e:
                    log_api_call(
                        method="GET",
                        url=f"{url}?knowledge_source_id={comparison_knowledge_source_id}&page={page}",
                        status_code=getattr(e.response, 'status_code', 0) if hasattr(e, 'response') else 0,
                        success=False,
                        details=f"Error fetching Ada articles page {page}: {str(e)}"
                    )
                    
                    with page_status:
                        st.error(f"❌ **Error fetching page {page}:** {str(e)}")
                    st.error(f"Error fetching articles from Ada: {str(e)}")
                    break
                
                time.sleep(0.1)  # Small delay to show progress
            
            if all_ada_articles:
                with main_status:
                    st.write("🔍 **Step 2/2:** Analyzing and comparing articles...")
                main_progress.progress(0.75)
                
                with comparison_container:
                    st.subheader("🔍 Article Analysis")
                    analysis_status = st.empty()
                    
                    with analysis_status:
                        st.write("🔄 **Comparing Grab articles with Ada articles...**")
                    
                    # Perform comparison
                    grab_articles = st.session_state.production_articles
                    
                    with analysis_status:
                        st.write(f"📊 **Analyzing {len(grab_articles)} Grab articles vs {len(all_ada_articles)} Ada articles...**")
                    
                    time.sleep(0.5)  # Small delay for visual effect
                    
                    comparison = compare_articles(grab_articles, all_ada_articles)
                    
                    # Store comparison results
                    st.session_state.comparison_results = comparison
                    st.session_state.comparison_knowledge_source_id = comparison_knowledge_source_id
                    
                    with analysis_status:
                        st.success("✅ **Analysis complete!**")
                
                main_progress.progress(1.0)
                
                with main_status:
                    st.write("🎉 **Comparison process completed successfully!**")
                
                # Display comparison results
                st.header("📊 Comparison Results")
                
                # Summary metrics
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("✅ Already in Ada", len(comparison['existing']))
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
                with st.expander(f"✅ Already in Ada ({len(comparison['existing'])})"):
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
                        st.session_state.articles_to_upload = comparison['new']
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
                                success, message = delete_ada_article(instance_name, api_key, article_id)
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
                st.error("Failed to fetch articles from Ada knowledge base")
else:
    st.info("👆 Please fetch articles from Grab first before comparing")
