"""
AI Rankings Fix - Replace the ranking subtabs section in app.py

To apply: Copy the content between START and END markers,
and replace the existing ranking subtabs section (lines ~720-774) in app.py
"""

# ========== START: REPLACE RANKING SUBTABS SECTION ==========

        with subtab_biggest:
            st.markdown("### 🏆 Biggest AI Companies / AI巨头")
            st.caption("Top AI companies by estimated valuation / 按估值排名的顶级AI公司")

            # Known AI giants/unicorns by valuation
            biggest_data = [
                {'Rank': 1, 'Company / 公司': 'OpenAI', 'Valuation / 估值': '$150B+', 'Category / 类别': 'Foundation Models'},
                {'Rank': 2, 'Company / 公司': 'ByteDance', 'Valuation / 估值': '$100B+', 'Category / 类别': 'Consumer AI'},
                {'Rank': 3, 'Company / 公司': 'Databricks', 'Valuation / 估值': '$50B+', 'Category / 类别': 'Data/ML Platform'},
                {'Rank': 4, 'Company / 公司': 'Anthropic', 'Valuation / 估值': '$18B+', 'Category / 类别': 'Foundation Models'},
                {'Rank': 5, 'Company / 公司': 'xAI', 'Valuation / 估值': '$15B+', 'Category / 类别': 'Foundation Models'},
                {'Rank': 6, 'Company / 公司': 'Scale AI', 'Valuation / 估值': '$14B+', 'Category / 类别': 'AI Infrastructure'},
                {'Rank': 7, 'Company / 公司': 'Perplexity', 'Valuation / 估值': '$9B', 'Category / 类别': 'AI Search'},
                {'Rank': 8, 'Company / 公司': 'Mistral AI', 'Valuation / 估值': '$6B', 'Category / 类别': 'Foundation Models'},
                {'Rank': 9, 'Company / 公司': 'Cohere', 'Valuation / 估值': '$5.5B', 'Category / 类别': 'Foundation Models'},
                {'Rank': 10, 'Company / 公司': 'Glean', 'Valuation / 估值': '$4.6B', 'Category / 类别': 'Enterprise AI'},
                {'Rank': 11, 'Company / 公司': 'Hugging Face', 'Valuation / 估值': '$4.5B', 'Category / 类别': 'AI Infrastructure'},
                {'Rank': 12, 'Company / 公司': 'Figure', 'Valuation / 估值': '$2.6B', 'Category / 类别': 'Robotics'},
                {'Rank': 13, 'Company / 公司': 'Runway', 'Valuation / 估值': '$1.5B', 'Category / 类别': 'AI Video'},
                {'Rank': 14, 'Company / 公司': 'ElevenLabs', 'Valuation / 估值': '$1.1B', 'Category / 类别': 'AI Audio'},
                {'Rank': 15, 'Company / 公司': 'Replicate', 'Valuation / 估值': '$1B', 'Category / 类别': 'AI Infrastructure'},
            ]
            df = pd.DataFrame(biggest_data)
            st.dataframe(df, use_container_width=True, hide_index=True)

        with subtab_upcoming:
            st.markdown("### 🚀 Rising Stars / 新兴之星")
            st.caption("Early-stage startups (Seed to Series B) / 早期创业公司 (种子轮到B轮)")

            # Get early-stage companies from shortlist
            EARLY_STAGES = ['seed', 'pre_seed', 'angel', 'series_a', 'series_b', 'pre_a']
            early_response = generate_shortlist(session, stages=EARLY_STAGES, limit=100)

            if early_response.entries:
                rising_data = [{
                    'Rank': i,
                    'Company / 公司': e.name,
                    'Stage / 轮次': e.funding_stage_zh or e.funding_stage or 'Unknown',
                    'Category / 类别': e.category_zh or e.category or 'AI',
                    'VCs': e.source_count,
                } for i, e in enumerate(early_response.entries[:30], 1)]
                df = pd.DataFrame(rising_data)
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.info("No early-stage companies found")

        with subtab_hottest:
            st.markdown("### 🔥 Hottest Right Now / 当前最热")
            st.caption("Most mentioned in this week's news / 本周新闻中提及最多的公司")

            # Try to get hot entities from cross-pipeline analyzer
            try:
                from utils.cross_pipeline_analyzer import CrossPipelineAnalyzer
                cache_dir = _app_dir / "data" / "cache" / "pipeline_contexts"
                if cache_dir.exists():
                    cpa = CrossPipelineAnalyzer(str(cache_dir))
                    target_date = st.session_state.get('selected_date', datetime.now().strftime('%Y-%m-%d'))
                    cpa.load_pipelines_for_date(target_date.replace('-', ''))

                    hot_entities = cpa.get_hot_entities(top_n=30)
                    company_entities = [e for e in hot_entities if e.entity_type == 'companies']

                    if company_entities:
                        hot_data = [{
                            'Rank': i,
                            'Company / 公司': e.entity_name,
                            'Mentions / 提及数': e.total_mentions,
                            'Pipelines': e.pipeline_count,
                        } for i, e in enumerate(company_entities[:25], 1)]
                        df = pd.DataFrame(hot_data)
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No company mentions in today's news yet")
                else:
                    st.info("Run news pipeline to see hottest companies")
            except Exception as e:
                st.info(f"News data not available - showing by VC backing instead")
                fallback = generate_shortlist(session, min_sources=2, limit=25)
                if fallback.entries:
                    df = pd.DataFrame([{
                        'Rank': i, 'Company / 公司': e.name, 'VCs': e.source_count,
                        'Category / 类别': e.category_zh or e.category or 'AI'
                    } for i, e in enumerate(fallback.entries, 1)])
                    st.dataframe(df, use_container_width=True, hide_index=True)

        with subtab_category:
            st.markdown("### 📊 By Category / 按类别")
            st.caption("Top AI companies per vertical / 各垂直领域顶级AI公司")

            all_response = generate_shortlist(session, limit=500)
            by_cat = defaultdict(list)
            for e in all_response.entries:
                cat = e.category_zh or e.category or 'uncategorized'
                by_cat[cat].append(e)

            cat_list = sorted(by_cat.items(), key=lambda x: len(x[1]), reverse=True)
            for cat, comps in cat_list[:12]:
                comps.sort(key=lambda x: x.source_count, reverse=True)
                with st.expander(f"**{cat}** ({len(comps)} companies)", expanded=(len(comps) > 20)):
                    df = pd.DataFrame([{'Company': c.name, 'VCs': c.source_count, 'Stage': c.funding_stage_zh or c.funding_stage or '-'} for c in comps[:10]])
                    st.dataframe(df, use_container_width=True, hide_index=True)

# ========== END: REPLACE RANKING SUBTABS SECTION ==========
