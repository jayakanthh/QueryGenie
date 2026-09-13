# QueryGenie Tier-2 faithful eval — self-contained Colab cell (run on a T4 GPU).
import subprocess, sys
subprocess.run([sys.executable,"-m","pip","install","-q","rapidfuzz","func_timeout","huggingface_hub","transformers","accelerate"])
import os, json, sqlite3, time, csv, datetime, zipfile
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from huggingface_hub import hf_hub_download

# --- download Spider databases (dev.json + database/*.sqlite) ---
z = hf_hub_download("HAL-9001/spider-databases","spider_data.zip",repo_type="dataset",local_dir="/content/spider")
if not os.path.exists("/content/spider/spider_data/dev.json"):
    with zipfile.ZipFile(z) as zf: zf.extractall("/content/spider")
SPIDER="/content/spider/spider_data"; DBDIR=os.path.join(SPIDER,"database")
def db_path(db_id): return os.path.join(DBDIR,db_id,db_id+".sqlite")

# ===== vendored: schema (db_utils) =====
import os
import sqlite3

from func_timeout import func_set_timeout, FunctionTimedOut

# get the database cursor for a sqlite database path
def get_cursor_from_path(sqlite_path):
    try:
        if not os.path.exists(sqlite_path):
            print("Openning a new connection %s" % sqlite_path)
        connection = sqlite3.connect(sqlite_path, check_same_thread = False)
    except Exception as e:
        print(sqlite_path)
        raise e
    connection.text_factory = lambda b: b.decode(errors="ignore")
    cursor = connection.cursor()
    return cursor

# execute predicted sql with a time limitation
@func_set_timeout(200)
def execute_sql(cursor, sql):
    cursor.execute(sql)

    return cursor.fetchall()

# execute predicted sql with a long time limitation (for buiding content index)
@func_set_timeout(2000)
def execute_sql_long_time_limitation(cursor, sql):
    cursor.execute(sql)

    return cursor.fetchall()

def check_sql_executability(generated_sql, db):
    if generated_sql.strip() == "":
        return "Error: empty string"
    try:
        cursor = get_cursor_from_path(db)
        # use `EXPLAIN QUERY PLAN` to avoid actually executing
        execute_sql(cursor, "EXPLAIN QUERY PLAN " + generated_sql)
        execution_error = None
    except FunctionTimedOut as fto:
        print("SQL execution time out error: {}.".format(fto))
        execution_error = "SQL execution times out."
    except Exception as e:
        print("SQL execution runtime error: {}.".format(e))
        execution_error = str(e)
    
    return execution_error

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False

def detect_special_char(name):
    for special_char in ['(', '-', ')', ' ', '/']:
        if special_char in name:
            return True

    return False

def add_quotation_mark(s):
    return "`" + s + "`"

def get_column_contents(column_name, table_name, cursor):
    select_column_sql = "SELECT DISTINCT `{}` FROM `{}` WHERE `{}` IS NOT NULL LIMIT 2;".format(column_name, table_name, column_name)
    results = execute_sql_long_time_limitation(cursor, select_column_sql)
    column_contents = [str(result[0]).strip() for result in results]
    # remove empty and extremely-long contents
    column_contents = [content for content in column_contents if len(content) != 0 and len(content) <= 25]

    return column_contents

def get_db_schema_sequence(schema):
    schema_sequence = "database schema :\n"
    for table in schema["schema_items"]:
        table_name, table_comment = table["table_name"], table["table_comment"]
        if detect_special_char(table_name):
            table_name = add_quotation_mark(table_name)
        
        # if table_comment != "":
        #     table_name += " ( comment : " + table_comment + " )"

        column_info_list = []
        for column_name, column_type, column_comment, column_content, pk_indicator in \
            zip(table["column_names"], table["column_types"], table["column_comments"], table["column_contents"], table["pk_indicators"]):
            if detect_special_char(column_name):
                column_name = add_quotation_mark(column_name)
            additional_column_info = []
            # column type
            additional_column_info.append(column_type)
            # pk indicator
            if pk_indicator != 0:
                additional_column_info.append("primary key")
            # column comment
            if column_comment != "":
                additional_column_info.append("comment : " + column_comment)
            # representive column values
            if len(column_content) != 0:
                additional_column_info.append("values : " + " , ".join(column_content))
            
            column_info_list.append(table_name + "." + column_name + " ( " + " | ".join(additional_column_info) + " )")
        
        schema_sequence += "table "+ table_name + " , columns = [ " + " , ".join(column_info_list) + " ]\n"

    if len(schema["foreign_keys"]) != 0:
        schema_sequence += "foreign keys :\n"
        for foreign_key in schema["foreign_keys"]:
            for i in range(len(foreign_key)):
                if detect_special_char(foreign_key[i]):
                    foreign_key[i] = add_quotation_mark(foreign_key[i])
            schema_sequence += "{}.{} = {}.{}\n".format(foreign_key[0], foreign_key[1], foreign_key[2], foreign_key[3])
    else:
        schema_sequence += "foreign keys : None\n"

    return schema_sequence.strip()

def get_matched_content_sequence(matched_contents):
    content_sequence = ""
    if len(matched_contents) != 0:
        content_sequence += "matched contents :\n"
        for tc_name, contents in matched_contents.items():
            table_name = tc_name.split(".")[0]
            column_name = tc_name.split(".")[1]
            if detect_special_char(table_name):
                table_name = add_quotation_mark(table_name)
            if detect_special_char(column_name):
                column_name = add_quotation_mark(column_name)
            
            content_sequence += table_name + "." + column_name + " ( " + " , ".join(contents) + " )\n"
    else:
        content_sequence = "matched contents : None"
    
    return content_sequence.strip()

def get_db_schema(db_path, db_comments, db_id):
    if db_id in db_comments:
        db_comment = db_comments[db_id]
    else:
        db_comment = None

    cursor = get_cursor_from_path(db_path)
    
    # obtain table names
    results = execute_sql(cursor, "SELECT name FROM sqlite_master WHERE type='table';")
    table_names = [result[0].lower() for result in results]

    schema = dict()
    schema["schema_items"] = []
    foreign_keys = []
    # for each table
    for table_name in table_names:
        # skip SQLite system table: sqlite_sequence
        if table_name == "sqlite_sequence":
            continue
        # obtain column names in the current table
        results = execute_sql(cursor, "SELECT name, type, pk FROM PRAGMA_TABLE_INFO('{}')".format(table_name))
        column_names_in_one_table = [result[0].lower() for result in results]
        column_types_in_one_table = [result[1].lower() for result in results]
        pk_indicators_in_one_table = [result[2] for result in results]

        column_contents = []
        for column_name in column_names_in_one_table:
            column_contents.append(get_column_contents(column_name, table_name, cursor))
        
        # obtain foreign keys in the current table
        results = execute_sql(cursor, "SELECT * FROM pragma_foreign_key_list('{}');".format(table_name))
        for result in results:
            if None not in [result[3], result[2], result[4]]:
                foreign_keys.append([table_name.lower(), result[3].lower(), result[2].lower(), result[4].lower()])
        
        # obtain comments for each schema item
        if db_comment is not None:
            if table_name in db_comment: # record comments for tables and columns
                table_comment = db_comment[table_name]["table_comment"]
                column_comments = [db_comment[table_name]["column_comments"][column_name] \
                    if column_name in db_comment[table_name]["column_comments"] else "" \
                        for column_name in column_names_in_one_table]
            else: # current database has comment information, but the current table does not
                table_comment = ""
                column_comments = ["" for _ in column_names_in_one_table]
        else: # current database has no comment information
            table_comment = ""
            column_comments = ["" for _ in column_names_in_one_table]

        schema["schema_items"].append({
            "table_name": table_name,
            "table_comment": table_comment,
            "column_names": column_names_in_one_table,
            "column_types": column_types_in_one_table,
            "column_comments": column_comments,
            "column_contents": column_contents,
            "pk_indicators": pk_indicators_in_one_table
        })
    
    schema["foreign_keys"] = foreign_keys
    
    return schema
# ===== vendored: value retriever (bridge) =====
"""
 Copyright (c) 2020, salesforce.com, inc.
 All rights reserved.
 SPDX-License-Identifier: BSD-3-Clause
 For full license text, see the LICENSE file in the repo root or https://opensource.org/licenses/BSD-3-Clause

 Encode DB content.
"""

import difflib
from typing import List, Optional, Tuple
from rapidfuzz import fuzz
import sqlite3
import functools

# fmt: off
_stopwords = {'who', 'ourselves', 'down', 'only', 'were', 'him', 'at', "weren't", 'has', 'few', "it's", 'm', 'again',
              'd', 'haven', 'been', 'other', 'we', 'an', 'own', 'doing', 'ma', 'hers', 'all', "haven't", 'in', 'but',
              "shouldn't", 'does', 'out', 'aren', 'you', "you'd", 'himself', "isn't", 'most', 'y', 'below', 'is',
              "wasn't", 'hasn', 'them', 'wouldn', 'against', 'this', 'about', 'there', 'don', "that'll", 'a', 'being',
              'with', 'your', 'theirs', 'its', 'any', 'why', 'now', 'during', 'weren', 'if', 'should', 'those', 'be',
              'they', 'o', 't', 'of', 'or', 'me', 'i', 'some', 'her', 'do', 'will', 'yours', 'for', 'mightn', 'nor',
              'needn', 'the', 'until', "couldn't", 'he', 'which', 'yourself', 'to', "needn't", "you're", 'because',
              'their', 'where', 'it', "didn't", 've', 'whom', "should've", 'can', "shan't", 'on', 'had', 'have',
              'myself', 'am', "don't", 'under', 'was', "won't", 'these', 'so', 'as', 'after', 'above', 'each', 'ours',
              'hadn', 'having', 'wasn', 's', 'doesn', "hadn't", 'than', 'by', 'that', 'both', 'herself', 'his',
              "wouldn't", 'into', "doesn't", 'before', 'my', 'won', 'more', 'are', 'through', 'same', 'how', 'what',
              'over', 'll', 'yourselves', 'up', 'mustn', "mustn't", "she's", 're', 'such', 'didn', "you'll", 'shan',
              'when', "you've", 'themselves', "mightn't", 'she', 'from', 'isn', 'ain', 'between', 'once', 'here',
              'shouldn', 'our', 'and', 'not', 'too', 'very', 'further', 'while', 'off', 'couldn', "hasn't", 'itself',
              'then', 'did', 'just', "aren't"}
# fmt: on

_commonwords = {"no", "yes", "many"}


def is_number(s: str) -> bool:
    try:
        float(s.replace(",", ""))
        return True
    except:
        return False


def is_stopword(s: str) -> bool:
    return s.strip() in _stopwords


def is_commonword(s: str) -> bool:
    return s.strip() in _commonwords


def is_common_db_term(s: str) -> bool:
    return s.strip() in ["id"]


class Match(object):
    def __init__(self, start: int, size: int) -> None:
        self.start = start
        self.size = size


def is_span_separator(c: str) -> bool:
    return c in "'\"()`,.?! "


def split(s: str) -> List[str]:
    return [c.lower() for c in s.strip()]


def prefix_match(s1: str, s2: str) -> bool:
    i, j = 0, 0
    for i in range(len(s1)):
        if not is_span_separator(s1[i]):
            break
    for j in range(len(s2)):
        if not is_span_separator(s2[j]):
            break
    if i < len(s1) and j < len(s2):
        return s1[i] == s2[j]
    elif i >= len(s1) and j >= len(s2):
        return True
    else:
        return False


def get_effective_match_source(s: str, start: int, end: int) -> Match:
    _start = -1

    for i in range(start, start - 2, -1):
        if i < 0:
            _start = i + 1
            break
        if is_span_separator(s[i]):
            _start = i
            break

    if _start < 0:
        return None

    _end = -1
    for i in range(end - 1, end + 3):
        if i >= len(s):
            _end = i - 1
            break
        if is_span_separator(s[i]):
            _end = i
            break

    if _end < 0:
        return None

    while _start < len(s) and is_span_separator(s[_start]):
        _start += 1
    while _end >= 0 and is_span_separator(s[_end]):
        _end -= 1

    return Match(_start, _end - _start + 1)


def get_matched_entries(
    s: str, field_values: List[str], m_theta: float = 0.85, s_theta: float = 0.85
) -> Optional[List[Tuple[str, Tuple[str, str, float, float, int]]]]:
    if not field_values:
        return None

    if isinstance(s, str):
        n_grams = split(s)
    else:
        n_grams = s

    matched = dict()
    for field_value in field_values:
        if not isinstance(field_value, str):
            continue
        fv_tokens = split(field_value)
        sm = difflib.SequenceMatcher(None, n_grams, fv_tokens)
        match = sm.find_longest_match(0, len(n_grams), 0, len(fv_tokens))
        if match.size > 0:
            source_match = get_effective_match_source(
                n_grams, match.a, match.a + match.size
            )
            if source_match: # and source_match.size > 1
                match_str = field_value[match.b : match.b + match.size]
                source_match_str = s[
                    source_match.start : source_match.start + source_match.size
                ]
                c_match_str = match_str.lower().strip()
                c_source_match_str = source_match_str.lower().strip()
                c_field_value = field_value.lower().strip()
                if c_match_str and not is_common_db_term(c_match_str): # and not is_number(c_match_str)
                    if (
                        is_stopword(c_match_str)
                        or is_stopword(c_source_match_str)
                        or is_stopword(c_field_value)
                    ):
                        continue
                    if c_source_match_str.endswith(c_match_str + "'s"):
                        match_score = 1.0
                    else:
                        if prefix_match(c_field_value, c_source_match_str):
                            match_score = fuzz.ratio(c_field_value, c_source_match_str) / 100
                        else:
                            match_score = 0
                    if (
                        is_commonword(c_match_str)
                        or is_commonword(c_source_match_str)
                        or is_commonword(c_field_value)
                    ) and match_score < 1:
                        continue
                    s_match_score = match_score
                    if match_score >= m_theta and s_match_score >= s_theta:
                        if field_value.isupper() and match_score * s_match_score < 1:
                            continue
                        matched[match_str] = (
                            field_value,
                            source_match_str,
                            match_score,
                            s_match_score,
                            match.size,
                        )
    
    if not matched:
        return None
    else:
        return sorted(
            matched.items(),
            key=lambda x: (1e16 * x[1][2] + 1e8 * x[1][3] + x[1][4]),
            reverse=True,
        )


@functools.lru_cache(maxsize=1000, typed=False)
def get_column_picklist(table_name: str, column_name: str, db_path: str) -> list:
    fetch_sql = "SELECT DISTINCT `{}` FROM `{}`".format(column_name, table_name)
    try:
        conn = sqlite3.connect(db_path)
        conn.text_factory = bytes
        c = conn.cursor()
        c.execute(fetch_sql)
        picklist = set()
        for x in c.fetchall():
            if isinstance(x[0], str):
                picklist.add(x[0].encode("utf-8"))
            elif isinstance(x[0], bytes):
                try:
                    picklist.add(x[0].decode("utf-8"))
                except UnicodeDecodeError:
                    picklist.add(x[0].decode("latin-1"))
            else:
                picklist.add(x[0])
        picklist = list(picklist)
    except Exception as e:
        picklist = []
    finally:
        conn.close()
    return picklist


def get_database_matches(
    question: str,
    table_name: str,
    column_name: str,
    db_path: str,
    top_k_matches: int = 2,
    match_threshold: float = 0.85,
) -> List[str]:
    picklist = get_column_picklist(
        table_name=table_name, column_name=column_name, db_path=db_path
    )
    # only maintain data in ``str'' type
    picklist = [ele.strip() for ele in picklist if isinstance(ele, str)]
    # picklist is unordered, we sort it to ensure the reproduction stability
    picklist = sorted(picklist)
    
    matches = []
    if picklist and isinstance(picklist[0], str):
        matched_entries = get_matched_entries(
            s=question,
            field_values=picklist,
            m_theta=match_threshold,
            s_theta=match_threshold,
        )

        if matched_entries:
            num_values_inserted = 0
            for _match_str, (
                field_value,
                _s_match_str,
                match_score,
                s_match_score,
                _match_size,
            ) in matched_entries:
                if "name" in column_name and match_score * s_match_score < 1:
                    continue
                if table_name != "sqlite_sequence":  # Spider database artifact
                    matches.append(field_value.strip())
                    num_values_inserted += 1
                    if num_values_inserted >= top_k_matches:
                        break
    return matches
# ---------------- eval ----------------
def run_sql(path, sql):
    try:
        con=sqlite3.connect(path); con.text_factory=lambda b:b.decode(errors="ignore")
        rows=con.execute(sql).fetchall(); con.close()
        return True, sorted([tuple(str(c) for c in r) for r in rows])
    except Exception:
        return False, None
def post_process(sql, schema_items):
    sql=sql.replace("\n"," ")
    for table in schema_items:
        for cn in table["column_names"]:
            if detect_special_char(cn) and cn in sql: sql=sql.replace(cn,"`"+cn+"`")
    while "``" in sql: sql=sql.replace("``","`")
    return sql
def clean_sql(t):
    t=t.strip().replace("```sql","").replace("```","").strip()
    return t.split(";")[0].strip()
def matched_contents_for(path, schema, question):
    fine={}
    for table in schema["schema_items"]:
        tname=table["table_name"]
        for cname in table["column_names"]:
            try: picklist=get_column_picklist(tname,cname,path)
            except Exception: continue
            picklist=sorted([e.strip() for e in picklist if isinstance(e,str) and e.strip()])
            if not picklist: continue
            fm=get_matched_entries(question,picklist)
            if not fm: continue
            tc=tname+"."+cname
            for _m,(fv,_s,ms,_sm,_sz) in fm:
                if ms<0.9: continue
                fv=fv.strip()
                if tc not in fine: fine[tc]=[]
                if len(fine[tc])<25 and fv not in fine[tc]: fine[tc].append(fv)
    return fine

MODEL=os.environ.get("QG_MODEL","seeklhy/codes-1b-spider")
RUN_ID=os.environ.get("QG_RUN_ID","T2-003")
print("model:",MODEL,"| run:",RUN_ID)
dev=json.load(open(os.path.join(SPIDER,"dev.json")))
device="cuda" if torch.cuda.is_available() else "cpu"
print("device:",device,"| examples:",len(dev))
tok=AutoTokenizer.from_pretrained(MODEL)
model=AutoModelForCausalLM.from_pretrained(MODEL,torch_dtype=torch.float16 if device=="cuda" else torch.float32).to(device).eval()
schema_cache={}
def schema_for(db_id):
    if db_id not in schema_cache:
        s=get_db_schema(db_path(db_id),{},db_id); schema_cache[db_id]=(s,get_db_schema_sequence(s))
    return schema_cache[db_id]
correct=pexec=0; t0=time.time()
for i,ex in enumerate(dev):
    db_id,question,gold=ex["db_id"],ex["question"],ex["query"]
    sch,schema_seq=schema_for(db_id)
    content_seq=get_matched_content_sequence(matched_contents_for(db_path(db_id),sch,question))
    prefix=schema_seq+"\n"+content_seq+"\n"+question+"\n"
    ids=[tok.bos_token_id]+tok(prefix,truncation=True,max_length=4096)["input_ids"]
    input_ids=torch.tensor([ids],device=device); attn=torch.ones_like(input_ids)
    with torch.no_grad():
        out=model.generate(input_ids=input_ids,attention_mask=attn,max_new_tokens=256,num_beams=4,num_return_sequences=4,pad_token_id=tok.eos_token_id)
    # Authors' text2sql_zero_shot.py: decode all 4 beams, post-process, keep the FIRST
    # candidate that passes EXPLAIN QUERY PLAN; fall back to beam 0.
    cands=[clean_sql(post_process(c,sch["schema_items"])) for c in
           tok.batch_decode(out[:,input_ids.shape[1]:],skip_special_tokens=True,clean_up_tokenization_spaces=False)]
    pred=next((c for c in cands if check_sql_executability(c,db_path(db_id)) is None), cands[0] if cands[0].strip() else "SQL placeholder")
    p_ok,p_rows=run_sql(db_path(db_id),pred); g_ok,g_rows=run_sql(db_path(db_id),gold)
    pexec+=p_ok; correct+=(p_ok and g_ok and p_rows==g_rows)
    if (i+1)%50==0 or i+1==len(dev):
        print(f"[{i+1}/{len(dev)}] EX={correct/(i+1):.4f} exec={pexec/(i+1):.2f} {(time.time()-t0)/(i+1):.1f}s/ex", flush=True)
n=len(dev)
print(f"\n==== FULL CodeS prompt | Spider dev EX = {correct/n:.4f} ({correct}/{n}) | executes {pexec/n:.3f} | {round(time.time()-t0)}s ====")
print("COPY THIS BACK:  %s %s EX=%.4f (%d/%d) executes=%.3f" % (RUN_ID,MODEL,correct/n,correct,n,pexec/n))
