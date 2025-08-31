import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import spacy
import pycountry
from io import StringIO
import base64
import ast
import itertools
from collections import Counter
from Bio import Entrez
from xml.etree import ElementTree as ET

# Set your Entrez email
Entrez.email = "your_email@example.com"  # Change this to your actual email

# Load NLP model
nlp = spacy.load("en_core_sci_md")

# Clinical whitelist
CLINICAL_TERMS = {
    "fever", "rash", "vomiting", "diarrhea", "cough", "headache", "fatigue",
    "dengue", "zika", "malaria", "cholera", "typhoid", "jaundice", "influenza",
    "sepsis", "tuberculosis", "hepatitis", "asthma", "covid-19",
    "sore throat", "shortness of breath", "nausea", "pain", "infection"
}

def clean_entity(e):
    return e.lower().strip() in CLINICAL_TERMS

st.title("🧬 PubMed NLP Dashboard for Emerging Clinical Patterns")

st.markdown("""
This app lets you:
- Upload PubMed abstract CSVs **or** Search PubMed
- Extract Symptoms, Diseases, and Countries
- Visualize clinical triplets and calculate **Threat Index**
""")

option = st.radio("Select Input Method", ["Upload CSV", "Search PubMed"])

def extract_entities(text):
    if pd.isna(text) or not isinstance(text, str):
        return []
    doc = nlp(text)
    return [ent.text.lower() for ent in doc.ents if len(ent.text) > 2]

def extract_countries(text):
    if pd.isna(text):
        return []
    country_list = [c.name.lower() for c in pycountry.countries]
    return [c for c in country_list if c in text.lower()]

def process_pipeline(df):
    df["Entities"] = df["Abstract"].apply(extract_entities)
    df["Countries"] = df["Abstract"].apply(extract_countries)

    # Parse year for trend analysis
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df["Year"] = df["Date"].dt.year

    df_clean = df[(df["Entities"].str.len() > 0) & (df["Countries"].str.len() > 0)].copy()

    triplet_counter = Counter()
    triplet_years = []

    for _, row in df_clean.iterrows():
        ents = [e.lower().strip() for e in row["Entities"] if clean_entity(e)]
        if len(ents) < 2:
            continue
        for country in row["Countries"]:
            for pair in itertools.combinations(set(ents), 2):
                symptom, disease = tuple(sorted(pair))
                triplet_counter[(symptom, disease, country.lower())] += 1
                if "Year" in row:
                    triplet_years.append({"Symptom": symptom, "Disease": disease, "Country": country.lower(), "Year": row["Year"]})

    summary = pd.DataFrame([
        {"Symptom": t[0], "Disease": t[1], "Country": t[2], "Count": c}
        for t, c in triplet_counter.items()
    ])
    if not summary.empty:
        summary = summary.sort_values(by="Count", ascending=False)
        summary["ThreatIndex"] = summary["Count"] / summary["Count"].max()

    trends = pd.DataFrame(triplet_years) if triplet_years else pd.DataFrame()
    return summary, trends

def get_csv_download_link(df):
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="clinical_triplets.csv">📥 Download Triplets CSV</a>'

# === Option 1: Upload CSV ===
if option == "Upload CSV":
    uploaded_file = st.file_uploader("📁 Upload PubMed Abstract CSV", type=["csv"])
    if uploaded_file:
        df = pd.read_csv(uploaded_file)
        st.success("✅ File uploaded successfully!")
        summary, trends = process_pipeline(df)

# === Option 2: Live PubMed Search ===
else:
    query = st.text_input("Enter PubMed Query (e.g., 'fever AND India')")
    start_date = st.date_input("Start Date")
    end_date = st.date_input("End Date")
    max_results = st.slider("Max Results", 100, 1000, step=100)
    if st.button("🔍 Search PubMed"):
        with st.spinner("Fetching data from PubMed..."):
            handle = Entrez.esearch(db="pubmed", term=query, retmax=max_results, datetype="pdat", mindate=start_date, maxdate=end_date)
            record = Entrez.read(handle)
            ids = record["IdList"]
            abstracts = []
            for pmid in ids:
                fetch = Entrez.efetch(db="pubmed", id=pmid, rettype="abstract", retmode="xml")
                root = ET.parse(fetch).getroot()
                for article in root.findall(".//PubmedArticle"):
                    title = article.findtext(".//ArticleTitle")
                    abstract = article.findtext(".//AbstractText")
                    date = article.findtext(".//PubDate/Year") or article.findtext(".//DateCompleted/Year")
                    abstracts.append({"Title": title, "Abstract": abstract, "Date": date})
            df = pd.DataFrame(abstracts)
            st.success(f"Retrieved {len(df)} articles")
            summary, trends = process_pipeline(df)

# === Display Results ===
if 'summary' in locals() and not summary.empty:
    st.subheader("📊 Top Clinical Triplets by Count")
    st.dataframe(summary.head(15))

    st.subheader("📈 Barplot of Top 10 Triplets")
    top10 = summary.head(10)
    fig, ax = plt.subplots(figsize=(10, 6))
    sns.barplot(x="Count", y=top10["Symptom"] + " | " + top10["Disease"] + " | " + top10["Country"], data=top10, ax=ax)
    ax.set_xlabel("Count")
    ax.set_ylabel("Triplet")
    st.pyplot(fig)

    st.subheader("🌍 Heatmap of Symptom–Country Co-occurrence")
    heatmap_data = summary.groupby(["Symptom", "Country"])["Count"].sum().unstack(fill_value=0)
    fig2, ax2 = plt.subplots(figsize=(12, 8))
    sns.heatmap(heatmap_data, cmap="YlOrRd", linewidths=0.5, ax=ax2)
    st.pyplot(fig2)

    # ✅ Time Trend Line Plot
    if 'trends' in locals() and not trends.empty:
        st.subheader("📅 Trend of Triplet Mentions Over Time")
        trends_count = trends.groupby("Year").size().reset_index(name="Triplet Mentions")
        fig3, ax3 = plt.subplots(figsize=(10, 5))
        sns.lineplot(data=trends_count, x="Year", y="Triplet Mentions", marker="o", ax=ax3)
        ax3.set_title("Annual Trend of Clinical Triplet Mentions")
        ax3.set_ylabel("Mentions")
        st.pyplot(fig3)

    st.markdown(get_csv_download_link(summary), unsafe_allow_html=True)
else:
    st.info("Awaiting data to process.")
