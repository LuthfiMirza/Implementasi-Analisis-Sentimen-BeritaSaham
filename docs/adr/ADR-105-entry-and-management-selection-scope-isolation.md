# ADR-105: Entry and Management Selection Scope Isolation

Status: Accepted

Entry reference selection and management reference selection use separate policies, evidence chains, gates, and approval bindings.

Entry policy cannot select management proposals, and management policy cannot select entry candidates. A final decision may expose neither or exactly one selected proposal, never both.
