import streamlit as st
from openai import OpenAI
import PyPDF2
import docx
import re
import textwrap

# ------------- Text Extraction Utilities -------------

def extract_text_from_pdf(pdf_file):
    pdf_reader = PyPDF2.PdfReader(pdf_file)
    text = ""
    for page in pdf_reader.pages:
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

# ------------- Normalization for Content-only Compare -------------

def normalize_content(text: str) -> str:
    """
    Normalize text to focus on content, not styling/formatting.
    - Normalize newlines and whitespace
    - Collapse multiple spaces
    - Remove common header/footer noise patterns (best effort)
    - Keep punctuation and sentence boundaries
    """
    if not text:
        return ""
    # Normalize line endings
    t = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove obvious page headers/footers if repetitive lines appear > 5 times
    lines = [ln.strip() for ln in t.split("\n")]
    freq = {}
    for ln in lines:
        if not ln:
            continue
        freq[ln] = freq.get(ln, 0) + 1
    common_noise = {ln for ln, c in freq.items() if c >= 5 and len(ln) <= 80}
    lines = [ln for ln in lines if ln not in common_noise]
    t = "\n".join(lines)
    # Collapse excessive whitespace
    t = re.sub(r"[ \t]+", " ", t)
    # Collapse multiple blank lines
    t = re.sub(r"\n{3,}", "\n\n", t)
    # Trim
    t = t.strip()
    return t

def chunk_text(s: str, max_chars: int = 6000):
    """
    Chunk text on paragraph boundaries to stay within model limits.
    """
    if len(s) <= max_chars:
        return [s]
    paras = s.split("\n\n")
    chunks, cur, cur_len = [], [], 0
    for p in paras:
        if cur_len + len(p) + 2 <= max_chars:
            cur.append(p)
            cur_len += len(p) + 2
        else:
            chunks.append("\n\n".join(cur))
            cur = [p]
            cur_len = len(p) + 2
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks

# ------------- LLM: Approval Analysis (original) -------------

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

# ------------- LLM: Content Comparison with Reasoning -------------

def llm_content_compare(client, doc1_norm: str, doc2_norm: str):
    """
    Compare content semantically, ignoring styling/formatting. Provide reasoned report.
    If texts are long, summarize chunks then provide a global judgment.
    """
    # Chunk if needed
    c1 = chunk_text(doc1_norm, max_chars=6000)
    c2 = chunk_text(doc2_norm, max_chars=6000)

    # If single-chunk each, do a direct compare
    if len(c1) == 1 and len(c2) == 1:
        return _llm_direct_compare(client, c1[0], c2[0])

    # Otherwise, compare chunk pairs and then ask the model for an overall synthesis
    per_chunk_results = []
    for i in range(max(len(c1), len(c2))):
        t1 = c1[i] if i < len(c1) else ""
        t2 = c2[i] if i < len(c2) else ""
        res = _llm_direct_compare(client, t1, t2, section_label=f"Section {i+1}")
        per_chunk_results.append(res)

    synthesis_prompt = f"""
You are comparing two long documents in multiple sections. Below are per-section comparison reports. Produce a single final report that:
- Judges whether the documents are identical in meaning, have only minor editorial differences, or contain substantive differences.
- Explains the key differences with solid reasoning.
- Lists examples/quotes (short snippets) to illustrate differences (if any).
- Ignores styling, typography, fonts, and minor formatting.

Possible Decision values:
- "IDENTICAL IN MEANING"
- "MINOR EDITS ONLY"
- "SUBSTANTIVE DIFFERENCES"

Per-section results:
{"\n\n".join(per_chunk_results)}

Respond in this exact format:
Decision: <one of the three values>

Reasoning:
- <bullet 1>
- <bullet 2>
- <bullet 3>

Key Differences (if any):
- <brief example or snippet and what changed>

Recommendations (if any):
- <how to align them or what to change>
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a rigorous content-comparison expert. Focus only on meaning, not styling or formatting."},
                {"role": "user", "content": synthesis_prompt}
            ],
            max_tokens=800,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error during content comparison synthesis: {str(e)}"

def _llm_direct_compare(client, t1: str, t2: str, section_label: str = None):
    section = f" ({section_label})" if section_label else ""
    prompt = f"""
Compare the content of two texts{section}. Focus only on meaning/semantics and substantive requirements. Ignore fonts, styles, headings, numbering changes, and superficial formatting.

Text A:
{t1}

Text B:
{t2}

Tasks:
1) Determine if Text B has the same meaning as Text A.
2) If there are differences, classify them as MINOR EDITS (wording/grammar/ordering with preserved meaning) or SUBSTANTIVE DIFFERENCES (policy, scope, conditions, figures, dates, obligations change).
3) Provide solid reasoning with specific references (short quotes or paraphrases). Keep it concise but concrete.

Respond in this exact format:
Decision: IDENTICAL IN MEANING / MINOR EDITS ONLY / SUBSTANTIVE DIFFERENCES

Reasoning:
- <bullet points with evidence>

Key Differences (if any):
- <short snippet or paraphrase comparison>

Recommendations (if any):
- <how to align B to A if needed>
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a rigorous content-comparison expert. Focus only on meaning, not styling or formatting."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=800,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error during content comparison: {str(e)}"

# ------------- Streamlit App -------------

def main():
    st.set_page_config(
        page_title="Proposal Approval Analyzer + Content Comparator (LLM)",
        page_icon="✅",
        layout="wide"
    )
    st.title("✅ Proposal Approval Analyzer + 🧠 Content Comparator (LLM)")
    st.markdown("Upload two documents. Choose Approval Analysis or Content-only Comparison powered by LLM reasoning.")

    # Sidebar mode selection
    mode = st.sidebar.radio(
        "Select Mode",
        ["Approval Analyzer", "Content Compare (LLM)"],
        index=0
    )

    # API key only needed when an LLM mode is used
    needs_llm = True  # both modes use LLM here
    client = None
    if needs_llm:
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
        doc1_file = st.file_uploader(
            "Upload Document 1",
            type=['pdf', 'docx', 'txt'],
            key="doc1"
        )
        if doc1_file:
            st.success(f"✅ {doc1_file.name} uploaded")
    
    with col2:
        st.subheader("📄 Document 2")
        doc2_file = st.file_uploader(
            "Upload Document 2",
            type=['pdf', 'docx', 'txt'],
            key="doc2"
        )
        if doc2_file:
            st.success(f"✅ {doc2_file.name} uploaded")

    if doc1_file and doc2_file:
        with st.spinner("Extracting text from documents..."):
            doc1_text_raw = get_document_text(doc1_file)
            doc2_text_raw = get_document_text(doc2_file)

        if not doc1_text_raw or not doc2_text_raw:
            st.error("Failed to extract text from one or both documents.")
            return

        # Previews
        with st.expander("📖 Document Previews (raw extracted text)"):
            c1, c2 = st.columns(2)
            with c1:
                st.subheader("Document 1")
                st.text_area("", doc1_text_raw[:1500] + ("..." if len(doc1_text_raw) > 1500 else ""), height=220, disabled=True)
            with c2:
                st.subheader("Document 2")
                st.text_area("", doc2_text_raw[:1500] + ("..." if len(doc2_text_raw) > 1500 else ""), height=220, disabled=True)

        # Normalized versions for content-only compare
        doc1_norm = normalize_content(doc1_text_raw)
        doc2_norm = normalize_content(doc2_text_raw)

        if mode == "Approval Analyzer":
            if st.button("🔍 Analyze Proposal for Approval", type="primary"):
                with st.spinner("Analyzing proposal against circular requirements..."):
                    analysis_result = analyze_document_approval(client, doc1_norm, doc2_norm)
                st.subheader("🎯 Approval Decision")
                if "APPROVED" in analysis_result.upper():
                    st.success("✅ PROPOSAL APPROVED")
                elif "REJECTED" in analysis_result.upper():
                    st.error("❌ PROPOSAL REJECTED")
                st.markdown(analysis_result)

                st.subheader("📊 Document Statistics")
                colA, colB, colC, colD = st.columns(4)
                with colA:
                    st.metric("Doc1 Words (normalized)", f"{len(doc1_norm.split())}")
                with colB:
                    st.metric("Doc2 Words (normalized)", f"{len(doc2_norm.split())}")
                with colC:
                    st.metric("Doc1 Characters", f"{len(doc1_norm):,}")
                with colD:
                    st.metric("Doc2 Characters", f"{len(doc2_norm):,}")

        else:  # Content Compare (LLM)
            if st.button("🧠 Compare Content (LLM)", type="primary"):
                with st.spinner("Comparing content with LLM (ignoring styling/formatting)..."):
                    result = llm_content_compare(client, doc1_norm, doc2_norm)

                st.subheader("🧾 LLM Content Comparison Result")
                st.markdown(result)

                # Quick verdict badge derived from Decision line
                decision_line = next((ln for ln in result.splitlines() if ln.strip().lower().startswith("decision:")), "")
                decision = decision_line.split(":", 1)[1].strip() if ":" in decision_line else ""
                if "IDENTICAL" in decision.upper():
                    st.success("✅ Identical in meaning")
                elif "MINOR" in decision.upper():
                    st.info("ℹ️ Minor edits only")
                elif "SUBSTANTIVE" in decision.upper():
                    st.warning("⚠️ Substantive differences")
                else:
                    st.info("Comparison complete")

    with st.expander("ℹ️ Notes"):
        st.markdown("""
        - Content-only comparison ignores fonts, typography, and superficial formatting.
        - We normalize whitespace and remove repetitive headers/footers where possible.
        - For very long documents, the app compares in sections, then synthesizes a global judgment.
        - If your PDFs are scans without selectable text, OCR is required (not included here).
        """)

    st.markdown("Built by SLEEKY @ BSPL AI Team | Content-first Comparison")

if __name__ == "__main__":
    main()
