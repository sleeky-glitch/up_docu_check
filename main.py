import streamlit as st
from openai import OpenAI
import PyPDF2
import docx
import difflib
import html
import re

# ------------- Text Extraction Utilities -------------

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
        # Some PDFs may return None for extract_text()
        page_text = page.extract_text() or ""
        text += page_text + "\n"
    return text

def extract_text_from_docx(docx_file):
    d = docx.Document(docx_file)
    text = ""
    for p in d.paragraphs:
        text += p.text + "\n"
    return text

def extract_text_from_txt(txt_file):
    # Handle both bytes and str streams
    content = txt_file.read()
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return str(content)

def get_document_text(uploaded_file):
    if uploaded_file is None:
        return None
    if uploaded_file.type == "application/pdf":
        return extract_text_from_pdf(uploaded_file)
    elif uploaded_file.type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return extract_text_from_docx(uploaded_file)
    elif uploaded_file.type == "text/plain":
        return extract_text_from_txt(uploaded_file)
    else:
        st.error("Unsupported file type. Please upload PDF, DOCX, or TXT files.")
        return None

# ------------- AI Analysis -------------

def analyze_document_approval(client, circular_text, proposal_text):
    prompt = f"""
    You are an expert reviewer. Document 1 is an official circular (policy/guideline/communication). Document 2 is a proposal that claims to be based on Document 1.

    Your task:
    1. Carefully read both documents.
    2. Decide if the proposal (Document 2) can be approved strictly on the basis of the circular (Document 1).
    3. If it can be approved, state "APPROVED" and briefly explain why.
    4. If it cannot be approved, state "REJECTED" and clearly list the reasons for rejection, referencing specific requirements or gaps.

    Document 1 (Circular):
    {circular_text[:3000]}

    Document 2 (Proposal):
    {proposal_text[:3000]}

    Please provide your answer in this format:
    Decision: APPROVED/REJECTED

    Explanation:
    (Your detailed reasoning here)

    Key Points Analysis:
    - Compliance with circular requirements
    - Missing elements (if any)
    - Alignment with stated policies
    - Recommendations for improvement (if rejected)
    """
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are an expert reviewer for proposals and circulars, specializing in compliance analysis and approval decisions."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.2
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error analyzing documents: {str(e)}"

# ------------- Diff Utilities -------------

def normalize_newlines(text: str) -> str:
    # Convert Windows/Mac newlines to \n
    return text.replace("\r\n", "\n").replace("\r", "\n")

def tokenize_words(s: str):
    # Simple word tokenizer that keeps punctuation as separate tokens
    return re.findall(r"\w+|[^\w\s]", s, re.UNICODE)

def word_level_diff(a_line: str, b_line: str) -> str:
    """
    Return an HTML string where deletions are wrapped in <del> and insertions in <ins>.
    This is for a single line comparison at word level.
    """
    a_tokens = tokenize_words(a_line)
    b_tokens = tokenize_words(b_line)
    sm = difflib.SequenceMatcher(a=a_tokens, b=b_tokens)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            segment = "".join(html.escape(tok) for tok in a_tokens[i1:i2])
            out.append(segment)
        elif tag == "delete":
            segment = "".join(html.escape(tok) for tok in a_tokens[i1:i2])
            out.append(f'<del style="background:#ffe0e0;text-decoration:line-through;color:#b30000">{segment}</del>')
        elif tag == "insert":
            segment = "".join(html.escape(tok) for tok in b_tokens[j1:j2])
            out.append(f'<ins style="background:#e0ffe6;text-decoration:none;color:#006600">{segment}</ins>')
        elif tag == "replace":
            del_seg = "".join(html.escape(tok) for tok in a_tokens[i1:i2])
            ins_seg = "".join(html.escape(tok) for tok in b_tokens[j1:j2])
            out.append(f'<del style="background:#ffe0e0;text-decoration:line-through;color:#b30000">{del_seg}</del>')
            out.append(f'<ins style="background:#e0ffe6;text-decoration:none;color:#006600">{ins_seg}</ins>')
    # Join and also preserve spaces between tokens where appropriate
    # Our tokenizer removed spaces; insert a space between alphanumerics and punctuation if needed is tricky.
    # To keep it simple, we will display tokens back-to-back; this is generally readable for highlighting.
    return "".join(out)

def side_by_side_diff(text1: str, text2: str) -> str:
    """
    Build a side-by-side HTML diff of two texts line-by-line.
    Uses word-level highlighting for modified lines.
    """
    text1 = normalize_newlines(text1)
    text2 = normalize_newlines(text2)
    lines1 = text1.split("\n")
    lines2 = text2.split("\n")

    sm = difflib.SequenceMatcher(a=lines1, b=lines2)

    # Build rows
    rows = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i1, i2):
                left = html.escape(lines1[k])
                right = html.escape(lines2[j1 + (k - i1)])
                rows.append((
                    "equal",
                    left,
                    right
                ))
        elif tag in ("replace", "delete", "insert"):
            # Handle line changes
            left_block = lines1[i1:i2]
            right_block = lines2[j1:j2]
            max_len = max(len(left_block), len(right_block))
            for idx in range(max_len):
                left_line = left_block[idx] if idx < len(left_block) else ""
                right_line = right_block[idx] if idx < len(right_block) else ""
                if left_line == right_line:
                    rows.append(("equal", html.escape(left_line), html.escape(right_line)))
                else:
                    # Word-level highlight
                    highlighted = word_level_diff(left_line, right_line)
                    # For left and right columns, split the highlighted string into del/ins dominant views
                    # Simpler: show both changes in both columns but with background to indicate side
                    left_view = highlighted
                    right_view = highlighted
                    rows.append(("change", left_view, right_view))

    # Build HTML table
    table_css = """
    <style>
    .diff-table {
        width: 100%;
        border-collapse: collapse;
        table-layout: fixed;
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 13px;
    }
    .diff-table th, .diff-table td {
        border: 1px solid #e5e7eb;
        vertical-align: top;
        padding: 6px 8px;
        white-space: pre-wrap;
        word-wrap: break-word;
    }
    .diff-equal { background: #ffffff; }
    .diff-change { background: #fffbea; }
    .diff-header {
        background: #f3f4f6;
        font-weight: 600;
        text-align: left;
    }
    .cell-index {
        width: 60px;
        color: #6b7280;
        background: #f9fafb;
        text-align: right;
        padding-right: 8px;
    }
    .cell-content {
        width: calc(50% - 60px);
    }
    del { text-decoration: line-through; }
    ins { text-decoration: none; }
    </style>
    """

    # Build table rows with line numbers
    html_rows = []
    left_line_no = 1
    right_line_no = 1

    for kind, left_html, right_html in rows:
        row_class = "diff-equal" if kind == "equal" else "diff-change"
        # increment line numbers based on presence of content
        left_num = left_line_no if left_html != "" else ""
        right_num = right_line_no if right_html != "" else ""
        if left_html != "":
            left_line_no += 1
        if right_html != "":
            right_line_no += 1

        html_rows.append(f"""
        <tr class="{row_class}">
            <td class="cell-index">{left_num}</td>
            <td class="cell-content">{left_html}</td>
            <td class="cell-index">{right_num}</td>
            <td class="cell-content">{right_html}</td>
        </tr>
        """)

    table = f"""
    {table_css}
    <table class="diff-table">
        <thead>
            <tr class="diff-header">
                <th>#</th>
                <th>Document 1</th>
                <th>#</th>
                <th>Document 2</th>
            </tr>
        </thead>
        <tbody>
            {''.join(html_rows)}
        </tbody>
    </table>
    """
    return table

def quick_equality_stats(text1: str, text2: str):
    # Basic stats for quick glance
    same = text1 == text2
    return {
        "exact_match": same,
        "len_doc1_chars": len(text1),
        "len_doc2_chars": len(text2),
        "len_doc1_words": len(text1.split()),
        "len_doc2_words": len(text2.split()),
    }

# ------------- Streamlit App -------------

def main():
    st.set_page_config(
        page_title="Proposal Approval Analyzer + Document Compare",
        page_icon="✅",
        layout="wide"
    )
    st.title("✅ Proposal Approval Analyzer + 🔎 Document Comparator")
    st.markdown("Upload a circular and a proposal for approval analysis, or compare two documents and highlight differences.")

    # Sidebar mode selection
    mode = st.sidebar.radio("Select Mode", ["Approval Analyzer", "Compare Documents"], index=0)

    # Get API key from Streamlit secrets (user never sees this)
    client = None
    if mode == "Approval Analyzer":
        if "openai" not in st.secrets or "api_key" not in st.secrets["openai"]:
            st.error("AI API key not found in app configuration. Please contact the administrator.")
            st.stop()
        api_key = st.secrets["openai"]["api_key"]
        try:
            client = OpenAI(api_key=api_key)
        except Exception:
            st.error("Error initializing AI backend. Please contact the administrator.")
            return

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("📋 Document 1")
        st.caption("Upload the first document (e.g., circular/policy)")
        doc1_file = st.file_uploader(
            "Upload Document 1",
            type=['pdf', 'docx', 'txt'],
            key="doc1"
        )
        if doc1_file:
            st.success(f"✅ {doc1_file.name} uploaded")
    
    with col2:
        st.subheader("📄 Document 2")
        st.caption("Upload the second document (e.g., proposal or revised version)")
        doc2_file = st.file_uploader(
            "Upload Document 2",
            type=['pdf', 'docx', 'txt'],
            key="doc2"
        )
        if doc2_file:
            st.success(f"✅ {doc2_file.name} uploaded")

    if doc1_file and doc2_file:
        with st.spinner("Extracting text from documents..."):
            doc1_text = get_document_text(doc1_file)
            doc2_text = get_document_text(doc2_file)

        if not doc1_text or not doc2_text:
            st.error("Failed to extract text from one or both documents.")
            return

        # Previews
        with st.expander("📖 Document Previews"):
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Document 1 Preview")
                st.text_area("", (doc1_text[:1000] + ("..." if len(doc1_text) > 1000 else "")), height=220, disabled=True)
            with c2:
                st.subheader("Document 2 Preview")
                st.text_area("", (doc2_text[:1000] + ("..." if len(doc2_text) > 1000 else "")), height=220, disabled=True)

        if mode == "Approval Analyzer":
            if st.button("🔍 Analyze Proposal for Approval", type="primary"):
                with st.spinner("Analyzing proposal against circular requirements..."):
                    analysis_result = analyze_document_approval(client, doc1_text, doc2_text)
                st.subheader("🎯 Approval Decision")
                if "APPROVED" in analysis_result.upper():
                    st.success("✅ PROPOSAL APPROVED")
                elif "REJECTED" in analysis_result.upper():
                    st.error("❌ PROPOSAL REJECTED")
                st.markdown(analysis_result)

                st.subheader("📊 Document Statistics")
                colA, colB, colC, colD = st.columns(4)
                with colA:
                    st.metric("Doc1 Length", f"{len(doc1_text.split())} words")
                with colB:
                    st.metric("Doc2 Length", f"{len(doc2_text.split())} words")
                with colC:
                    st.metric("Doc1 Characters", f"{len(doc1_text):,}")
                with colD:
                    st.metric("Doc2 Characters", f"{len(doc2_text):,}")

        else:  # Compare Documents
            st.subheader("🧮 Quick Comparison")
            stats = quick_equality_stats(doc1_text, doc2_text)
            if stats["exact_match"]:
                st.success("✅ Documents are EXACTLY identical.")
            else:
                st.warning("⚠️ Documents differ.")

            colA, colB, colC, colD = st.columns(4)
            with colA:
                st.metric("Doc1 Words", f"{stats['len_doc1_words']}")
            with colB:
                st.metric("Doc2 Words", f"{stats['len_doc2_words']}")
            with colC:
                st.metric("Doc1 Chars", f"{stats['len_doc1_chars']:,}")
            with colD:
                st.metric("Doc2 Chars", f"{stats['len_doc2_chars']:,}")

            st.subheader("🧩 Differences (Side-by-Side)")
            st.caption("Green = insertions; Red strikethrough = deletions. Yellow rows indicate changed lines.")
            diff_html = side_by_side_diff(doc1_text, doc2_text)
            st.components.v1.html(diff_html, height=600, scrolling=True)

    with st.expander("ℹ️ How to use"):
        st.markdown("""
        1. Upload Document 1 and Document 2.
        2. Select the desired mode from the sidebar:
           - Approval Analyzer: Decide if Document 2 (proposal) can be approved based on Document 1 (circular).
           - Compare Documents: Check if both documents are the same and view highlighted differences.
        3. Click the action button to run the selected operation.
        
        What happens:
        - Approval Analyzer compares proposal against circular and returns APPROVED/REJECTED with reasoning.
        - Compare Documents provides equality status, basic stats, and a side-by-side diff with highlights.
        """)

    st.markdown("Built by SLEEKY @ BSPL AI Team | Proposal Approval Analyzer + Comparator")

if __name__ == "__main__":
    main()
