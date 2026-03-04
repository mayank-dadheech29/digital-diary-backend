file_path = "app/api/v1/endpoints/search.py"

with open(file_path, "r") as f:
    content = f.read()

# Replace TRANSACTIONS structured fallback logic so it stops enforcing text searches blindly over exact numerical matches
old_struct_tx = """        if lexical:
            stmt = stmt.where(or_(*lexical))"""

new_struct_tx = """        # Only force lexical searches in structured mode if we haven't already explicitly satisfied the search via direct amount/numeric intent filters to prevent '1050' AND 'title contains 1050' collapsing query results to zero.
        if lexical and not (f and (f.amount_gt is not None or f.amount_lt is not None or f.created_after)):
            stmt = stmt.where(or_(*lexical))"""

content = content.replace(old_struct_tx, new_struct_tx)

with open(file_path, "w") as f:
    f.write(content)
print("Updated structured fallback preventing numeric collapse!")
