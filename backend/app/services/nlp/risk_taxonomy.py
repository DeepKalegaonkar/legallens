"""Shared risk category taxonomy for the trained risk classifier.

The category names match the CUAD (Contract Understanding Atticus Dataset)
question labels used to train `risk_classifier.joblib` in
`ml_training/train_risk_classifier.py`. Both the training script and the
runtime `TrainedClauseAnalyzer` import this module so the label set, severity
mapping, and explanations never drift apart.
"""

from app.models.risk_finding import RiskSeverity

# CUAD category name -> severity, for the categories that genuinely indicate risk.
RISK_CATEGORY_SEVERITY: dict[str, RiskSeverity] = {
    "Uncapped Liability": RiskSeverity.HIGH,
    "Liquidated Damages": RiskSeverity.HIGH,
    "Covenant Not To Sue": RiskSeverity.HIGH,
    "Irrevocable Or Perpetual License": RiskSeverity.HIGH,
    "Non-Compete": RiskSeverity.MEDIUM,
    "Exclusivity": RiskSeverity.MEDIUM,
    "Change Of Control": RiskSeverity.MEDIUM,
    "Termination For Convenience": RiskSeverity.MEDIUM,
    "Anti-Assignment": RiskSeverity.MEDIUM,
    "Ip Ownership Assignment": RiskSeverity.MEDIUM,
    "Minimum Commitment": RiskSeverity.MEDIUM,
    "Volume Restriction": RiskSeverity.MEDIUM,
    "Rofr/Rofo/Rofn": RiskSeverity.MEDIUM,
    "No-Solicit Of Employees": RiskSeverity.LOW,
    "No-Solicit Of Customers": RiskSeverity.LOW,
    "Non-Disparagement": RiskSeverity.LOW,
    "Audit Rights": RiskSeverity.LOW,
    "Non-Transferable License": RiskSeverity.LOW,
    "Revenue/Profit Sharing": RiskSeverity.LOW,
}

RISK_CATEGORY_EXPLANATIONS: dict[str, str] = {
    "Uncapped Liability": "Liability under this clause does not appear to be capped, exposing a party to unlimited financial risk.",
    "Liquidated Damages": "Specifies a predetermined damages amount that may be disproportionate to actual harm.",
    "Covenant Not To Sue": "Waives the right to bring legal claims, which can foreclose important remedies.",
    "Irrevocable Or Perpetual License": "Grants a license that cannot be revoked or that never expires, permanently limiting the grantor's rights.",
    "Non-Compete": "Restricts future business activity, which may be overly broad or unenforceable in some jurisdictions.",
    "Exclusivity": "Requires dealing exclusively with one party, limiting flexibility to work with others.",
    "Change Of Control": "Triggers rights or obligations if ownership of a party changes, which can complicate M&A activity.",
    "Termination For Convenience": "Allows termination without cause, creating uncertainty for the other party.",
    "Anti-Assignment": "Restricts the ability to assign or transfer the contract, limiting flexibility in a sale or reorganization.",
    "Ip Ownership Assignment": "Assigns ownership of intellectual property to the other party, which may give up valuable rights.",
    "Minimum Commitment": "Obligates a minimum purchase, spend, or volume regardless of actual need.",
    "Volume Restriction": "Caps or restricts volume, which may limit growth or operational flexibility.",
    "Rofr/Rofo/Rofn": "Grants a right of first refusal, first offer, or first negotiation that can constrain future deals with third parties.",
    "No-Solicit Of Employees": "Restricts hiring or soliciting the other party's employees.",
    "No-Solicit Of Customers": "Restricts soliciting the other party's customers.",
    "Non-Disparagement": "Restricts negative statements about the other party, which can limit honest public commentary.",
    "Audit Rights": "Grants audit rights that may impose ongoing compliance and disclosure burdens.",
    "Non-Transferable License": "Grants a license that cannot be transferred, limiting flexibility in a sale or restructuring.",
    "Revenue/Profit Sharing": "Imposes an ongoing obligation to share revenue or profits with the other party.",
}

# Maps the string labels produced by severity_classifier.joblib (trained on
# final_merged_dataset.csv: CUAD clauses + a real Indian legal-contract-clauses
# dataset) to the shared RiskSeverity enum.
SEVERITY_LABEL_TO_ENUM: dict[str, RiskSeverity] = {
    "Low": RiskSeverity.LOW,
    "Medium": RiskSeverity.MEDIUM,
    "High": RiskSeverity.HIGH,
}

# Used when the severity model alone (not the CUAD category model) flags a
# clause as risky -- i.e. the clause doesn't match one of the 19 specific
# categories above, but reads as risky per the broader, India-inclusive
# training set.
GENERAL_RISK_TYPE = "general_risk_language"
GENERAL_RISK_EXPLANATION = (
    "Flagged as potentially risky by a general-purpose severity model trained on a broader, "
    "India-inclusive contract dataset, even though it doesn't match one of the specific risk "
    "categories above."
)
