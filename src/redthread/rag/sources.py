"""Regulatory documents ingested for GraphRAG. Downloaded to docs/regulatory/ (git-ignored) by
``python scripts/build_knowledge.py --fetch``. URLs are the ones listed in data/README.md."""

SOURCES: dict[str, tuple[str, str]] = {
    # file name: (title, url)
    "fincen_sar_narrative_guidance.pdf": (
        "FinCEN: Guidance on Preparing a Complete and Sufficient SAR Narrative",
        "https://www.fincen.gov/system/files/shared/sar_guidance_narrative.pdf"),
    "fincen_sar_complete_sufficient_narrative.pdf": (
        "FinCEN: Preparing a Complete and Sufficient SAR Narrative",
        "https://www.fincen.gov/system/files/shared/sarnarrcompletguidfinal_112003.pdf"),
    "fincen_sar_supporting_documentation.pdf": (
        "FinCEN: SAR Supporting Documentation (FIN-2007-G003)",
        "https://www.fincen.gov/system/files/shared/fin-2007-g003.pdf"),
    "fincen_sar_faqs_2025.pdf": (
        "FinCEN: SAR Filing FAQs, October 2025",
        "https://www.fincen.gov/system/files/2025-10/SAR-FAQs-October-2025.pdf"),
    "fincen_identity_related_2021.pdf": (
        "FinCEN: Identity-Related Suspicious Activity, 2021",
        "https://www.fincen.gov/system/files/shared/FTA_Identity_Final508.pdf"),
    "fincen_imposter_money_mule_2020.pdf": (
        "FinCEN: Advisory on Imposter Scams and Money Mule Schemes",
        "https://www.fincen.gov/system/files/advisory/2020-07-07/Advisory_%20Imposter_and_Money_Mule_COVID_19_508_FINAL.pdf"),
    "fincen_account_takeover_advisory.html": (
        "FinCEN: Advisory on Account Takeover Activity (FIN-2011-A016)",
        "https://www.fincen.gov/resources/advisories/fincen-advisory-fin-2011-a016"),
    "ffiec_red_flags.html": (
        "FFIEC: Money Laundering and Terrorist Financing Red Flags",
        "https://bsaaml.ffiec.gov/manual/Appendices/07"),
    "ffiec_suspicious_activity_reporting.html": (
        "FFIEC: Suspicious Activity Reporting",
        "https://bsaaml.ffiec.gov/manual/AssessingComplianceWithBSARegulatoryRequirements/04"),
    "fatf_cyber_enabled_fraud.pdf": (
        "FATF: Illicit Financial Flows from Cyber-Enabled Fraud",
        "https://www.fatf-gafi.org/content/dam/fatf-gafi/reports/Illicit-financial-flows-cyber-enabled-fraud.pdf.coredownload.inline.pdf"),
    "fincen_sar_activity_review.pdf": (
        "FinCEN: SAR Activity Review - Trends, Tips and Issues",
        "https://www.fincen.gov/sites/default/files/sar_report/sar_tti_19.pdf"),
    "ofac_sdn_list.pdf": (
        "OFAC: Specially Designated Nationals list",
        "https://www.treasury.gov/ofac/downloads/sdnlist.pdf"),
    "fatf_new_payment_methods.html": (
        "FATF: Money Laundering Using New Payment Methods",
        "https://www.fatf-gafi.org/en/publications/Methodsandtrends/Reportonnewpaymentmethods.html"),
    "fatf_professional_money_laundering.html": (
        "FATF: Professional Money Laundering",
        "https://www.fatf-gafi.org/en/publications/Methodsandtrends/Professional-money-laundering.html"),
    "fatf_remittance_currency_exchange.html": (
        "FATF: Money Laundering through Remittance and Currency Exchange Providers",
        "https://www.fatf-gafi.org/en/publications/Methodsandtrends/Moneylaunderingthroughmoneyremittanceandcurrencyexchangeproviders.html"),
    "fatf_trade_based_money_laundering.html": (
        "FATF: Trade-Based Money Laundering",
        "https://www.fatf-gafi.org/en/publications/Methodsandtrends/Trade-based-money-laundering-trends-and-developments.html"),
    "fatf_international_cooperation.html": (
        "FATF: International Co-operation on ML Detection, Investigation and Prosecution",
        "https://www.fatf-gafi.org/en/publications/Methodsandtrends/international-cooperation-against-money-laundering.html"),
}
