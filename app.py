if st.button("🔄 Fetch Articles from Grab", type="primary"):
    with st.spinner("Fetching articles from Grab..."):
        data = fetch_grab_data(user_type, language_locale)
        
        if data:
            all_articles = extract_articles(data)
            
            # DEBUG: Show what fields are available in the first article
            if all_articles and user_type == "moveit":
                st.subheader("🔍 DEBUG: First Article Structure")
                st.write("**Available fields in first article:**")
                if 'articles' in data and len(data['articles']) > 0:
                    first_article_raw = data['articles'][0]
                    st.json(first_article_raw)
                    st.write("**Keys available:**", list(first_article_raw.keys()))
            
            # Apply MoveIt filtering if needed
            if user_type == "moveit":
                original_count = len(all_articles)
                
                # DEBUG: Check a few articles for the fields
                st.write("**DEBUG: Checking first 3 articles for category/section IDs:**")
                for i, article in enumerate(all_articles[:3]):
                    st.write(f"Article {i+1}:")
                    st.write(f"  - ID: {article.get('id')}")
                    st.write(f"  - Name: {article.get('name', 'N/A')[:50]}")
                    st.write(f"  - category_id: {article.get('category_id', 'NOT FOUND')}")
                    st.write(f"  - section_id: {article.get('section_id', 'NOT FOUND')}")
                
                all_articles = filter_moveit_articles(all_articles)
                st.info(f"📍 MoveIt Filter: {len(all_articles)} articles (from category 10000024, sections 40001122-40001341) out of {original_count} total")
