import re

file_path = "app/api/v1/endpoints/search.py"

with open(file_path, "r") as f:
    content = f.read()

old_block = """    intent = normalize_intent(intent, raw_query, request_limit)

    structured_result = await run_structured_search(intent, user_id, db, request_limit)

    financial_summary"""

new_block = """    intent = normalize_intent(intent, raw_query, request_limit)

    if intent.use_vector_search:
        query_embedding = await request.app.state.ai.get_embedding(intent.optimized_query or raw_query)
        if query_embedding:
            structured_result = await run_hybrid_search(
                intent=intent,
                query_embedding=query_embedding,
                optimized_query=intent.optimized_query or raw_query,
                user_id=user_id,
                db=db,
                limit=request_limit,
                threshold=threshold
            )
        else:
            structured_result = await run_structured_search(intent, user_id, db, request_limit)
    else:
        structured_result = await run_structured_search(intent, user_id, db, request_limit)

    financial_summary"""

content = content.replace(old_block, new_block)

with open(file_path, "w") as f:
    f.write(content)

print("Updated search logic!")
