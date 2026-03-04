file_path = "app/api/v1/endpoints/search.py"

with open(file_path, "r") as f:
    content = f.read()

# Replace ENTRIES in hybrid_search
old_entry = """        if term:
            lexical.extend([Entry.title.ilike(term), Entry.content.ilike(term)])

        kw_clause = build_keyword_or([Entry.title, Entry.content], keywords)
        if kw_clause is not None:
            lexical.append(kw_clause)

        stmt = select(Entry).where(
            Entry.user_id == user_id,
            or_(
                and_(Entry.embedding.is_not(None), Entry.embedding.cosine_distance(query_embedding) < threshold),
                *lexical,
            ),
        )"""

new_entry = """        stmt = select(Entry).where(
            Entry.user_id == user_id,
            and_(Entry.embedding.is_not(None), Entry.embedding.cosine_distance(query_embedding) < threshold),
        )"""


# Replace TRANSACTIONS in hybrid_search
old_tx = """        if term:
            lexical.extend([
                Transaction.title.ilike(term),
                Transaction.description.ilike(term),
                Contact.full_name.ilike(term),
            ])
            if ts_query is not None:
                lexical.append(Transaction.search_text.op("@@")(ts_query))

        kw_clause = build_keyword_or([Transaction.title, Transaction.description, Contact.full_name], keywords)
        if kw_clause is not None:
            lexical.append(kw_clause)

        stmt = select(Transaction).outerjoin(Contact, Transaction.contact_id == Contact.id).where(
            Transaction.user_id == user_id,
            or_(
                and_(Transaction.embedding.is_not(None), Transaction.embedding.cosine_distance(query_embedding) < (threshold + 0.10)),
                *lexical,
            ),
        )"""

new_tx = """        stmt = select(Transaction).outerjoin(Contact, Transaction.contact_id == Contact.id).where(
            Transaction.user_id == user_id,
            and_(Transaction.embedding.is_not(None), Transaction.embedding.cosine_distance(query_embedding) < threshold)
        )"""


# Replace CONTACTS in hybrid search
old_ct = """        if term:
            lexical.extend([
                Contact.full_name.ilike(term),
                Contact.primary_org.ilike(term),
                Contact.primary_title.ilike(term),
                cast(Contact.dynamic_details, String).ilike(term),
            ])
            if ts_query is not None:
                lexical.append(Contact.search_text.op("@@")(ts_query))

        kw_clause = build_keyword_or(
            [Contact.full_name, Contact.primary_org, Contact.primary_title, cast(Contact.dynamic_details, String)],
            keywords,
        )
        if kw_clause is not None:
            lexical.append(kw_clause)

        stmt = select(Contact).where(
            Contact.user_id == user_id,
            or_(
                and_(Contact.embedding.is_not(None), Contact.embedding.cosine_distance(query_embedding) < threshold),
                *lexical,
            ),
        )"""
        
new_ct = """        stmt = select(Contact).where(
            Contact.user_id == user_id,
            and_(Contact.embedding.is_not(None), Contact.embedding.cosine_distance(query_embedding) < threshold)
        )"""


content = content.replace(old_entry, new_entry)
content = content.replace(old_tx, new_tx)
content = content.replace(old_ct, new_ct)

with open(file_path, "w") as f:
    f.write(content)
print("Updated!")
