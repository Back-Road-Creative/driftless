# PMBOK 8 crosswalk

`driftless/pmbok/catalog.py`'s 49 processes are a versioned-in-code copy of the PMBOK 6
process-group x knowledge-area grid (`docs/pmbok-mapping.md` explains why the tool keeps
that edition as its ITTO catalog). JP's team works from the PMBOK Guide 8th edition, which
drops the 49-process grid for 40 processes across seven domains plus five "focus areas"
that replace the old process groups. This table is **an editorial crosswalk, not PMI's** —
PMI had not published the 8th edition's own text at the time of writing, so this crosswalk
is built from two secondary sources, brainbok.com and projinsights.com (both 2026), not
PMI's own materials. Treat every PMBOK 8 process/domain name below as unverified against
PMI's text and offered only as orientation for a reader arriving from the newer edition.
It changes nothing about the catalog itself.

`tests/test_docs_pmbok8_crosswalk.py` checks the table against the live catalog: the process
id/name columns must match `catalog.PROCESSES` exactly, and every PMBOK 8 process cell must
be one of the 40 names below (or one of the two dash markers), so a catalog change or a typo
turns this doc red rather than letting it drift.

## The 40 PMBOK 8 processes, by domain

Per brainbok.com and projinsights.com (2026). The five focus areas — Initiating, Planning,
Executing, Monitoring and Controlling, Closing — replace the old process groups and are not
tracked per-process here.

- **Governance:** Initiate Project or Phase; Integrate and Align Project Plans; Manage
  Project Execution; Manage Project Knowledge; Manage Quality Assurance; Monitor and Control
  Project Performance; Assess and Implement Changes; Plan Sourcing Strategy; Close Project
  or Phase
- **Scope:** Plan Scope Management; Elicit and Analyze Requirements; Define Scope; Develop
  Scope Structure; Validate Scope; Monitor and Control Scope
- **Schedule:** Plan Schedule Management; Develop Schedule; Monitor and Control Schedule
- **Finance:** Plan Financial Management; Estimate Costs; Develop Budget; Monitor and
  Control Finances
- **Stakeholders:** Identify Stakeholders; Plan Stakeholder Engagement; Plan Communications
  Management; Manage Stakeholder Engagement; Manage Communications; Monitor Communications;
  Monitor Stakeholder Engagement
- **Resources:** Plan Resource Management; Estimate Resources; Acquire Resources; Lead the
  Team; Monitor and Control Resourcing
- **Risk:** Plan Risk Management; Identify Risks; Perform Risk Analysis; Plan Risk
  Responses; Implement Risk Responses; Monitor Risks

Two catalog processes, `Conduct Procurements` and `Control Procurements`, moved to an
appendix in these sources and are not among the 40; two more, `Plan Quality Management` and
`Control Quality`, have no direct PMBOK 8 process in these sources (absorbed into
`Manage Quality Assurance`'s broader scope). Both cases are marked with a dash in the table
below rather than forced onto a process they do not name.

## The table

A 49-to-40 crosswalk merges several PMBOK 6 processes onto one PMBOK 8 process (for example
`Define Activities`, `Sequence Activities`, `Estimate Activity Durations` and
`Develop Schedule` all feed PMBOK 8's single `Develop Schedule`).

| ID | Process | PMBOK 8 process | PMBOK 8 domain |
| --- | --- | --- | --- |
| 4.1 | Develop Project Charter | Initiate Project or Phase | Governance |
| 4.2 | Develop Project Management Plan | Integrate and Align Project Plans | Governance |
| 4.3 | Direct and Manage Project Work | Manage Project Execution | Governance |
| 4.4 | Manage Project Knowledge | Manage Project Knowledge | Governance |
| 4.5 | Monitor and Control Project Work | Monitor and Control Project Performance | Governance |
| 4.6 | Perform Integrated Change Control | Assess and Implement Changes | Governance |
| 4.7 | Close Project or Phase | Close Project or Phase | Governance |
| 5.1 | Plan Scope Management | Plan Scope Management | Scope |
| 5.2 | Collect Requirements | Elicit and Analyze Requirements | Scope |
| 5.3 | Define Scope | Define Scope | Scope |
| 5.4 | Create WBS | Develop Scope Structure | Scope |
| 5.5 | Validate Scope | Validate Scope | Scope |
| 5.6 | Control Scope | Monitor and Control Scope | Scope |
| 6.1 | Plan Schedule Management | Plan Schedule Management | Schedule |
| 6.2 | Define Activities | Develop Schedule | Schedule |
| 6.3 | Sequence Activities | Develop Schedule | Schedule |
| 6.4 | Estimate Activity Durations | Develop Schedule | Schedule |
| 6.5 | Develop Schedule | Develop Schedule | Schedule |
| 6.6 | Control Schedule | Monitor and Control Schedule | Schedule |
| 7.1 | Plan Cost Management | Plan Financial Management | Finance |
| 7.2 | Estimate Costs | Estimate Costs | Finance |
| 7.3 | Determine Budget | Develop Budget | Finance |
| 7.4 | Control Costs | Monitor and Control Finances | Finance |
| 8.1 | Plan Quality Management | — (absorbed) | — (absorbed) |
| 8.2 | Manage Quality | Manage Quality Assurance | Governance |
| 8.3 | Control Quality | — (absorbed) | — (absorbed) |
| 9.1 | Plan Resource Management | Plan Resource Management | Resources |
| 9.2 | Estimate Activity Resources | Estimate Resources | Resources |
| 9.3 | Acquire Resources | Acquire Resources | Resources |
| 9.4 | Develop Team | Lead the Team | Resources |
| 9.5 | Manage Team | Lead the Team | Resources |
| 9.6 | Control Resources | Monitor and Control Resourcing | Resources |
| 10.1 | Plan Communications Management | Plan Communications Management | Stakeholders |
| 10.2 | Manage Communications | Manage Communications | Stakeholders |
| 10.3 | Monitor Communications | Monitor Communications | Stakeholders |
| 11.1 | Plan Risk Management | Plan Risk Management | Risk |
| 11.2 | Identify Risks | Identify Risks | Risk |
| 11.3 | Perform Qualitative Risk Analysis | Perform Risk Analysis | Risk |
| 11.4 | Perform Quantitative Risk Analysis | Perform Risk Analysis | Risk |
| 11.5 | Plan Risk Responses | Plan Risk Responses | Risk |
| 11.6 | Implement Risk Responses | Implement Risk Responses | Risk |
| 11.7 | Monitor Risks | Monitor Risks | Risk |
| 12.1 | Plan Procurement Management | Plan Sourcing Strategy | Governance |
| 12.2 | Conduct Procurements | — (appendix) | — (appendix) |
| 12.3 | Control Procurements | — (appendix) | — (appendix) |
| 13.1 | Identify Stakeholders | Identify Stakeholders | Stakeholders |
| 13.2 | Plan Stakeholder Engagement | Plan Stakeholder Engagement | Stakeholders |
| 13.3 | Manage Stakeholder Engagement | Manage Stakeholder Engagement | Stakeholders |
| 13.4 | Monitor Stakeholder Engagement | Monitor Stakeholder Engagement | Stakeholders |

## Which catalog processes feed each PMBOK 8 process

All 40 PMBOK 8 processes are fed by at least one catalog process above; none are listed as
not fed by the catalog.

- Governance: Initiate Project or Phase (4.1); Integrate and Align Project Plans (4.2);
  Manage Project Execution (4.3); Manage Project Knowledge (4.4); Manage Quality Assurance
  (8.2); Monitor and Control Project Performance (4.5); Assess and Implement Changes (4.6);
  Plan Sourcing Strategy (12.1); Close Project or Phase (4.7)
- Scope: Plan Scope Management (5.1); Elicit and Analyze Requirements (5.2); Define Scope
  (5.3); Develop Scope Structure (5.4); Validate Scope (5.5); Monitor and Control Scope (5.6)
- Schedule: Plan Schedule Management (6.1); Develop Schedule (6.2, 6.3, 6.4, 6.5); Monitor
  and Control Schedule (6.6)
- Finance: Plan Financial Management (7.1); Estimate Costs (7.2); Develop Budget (7.3);
  Monitor and Control Finances (7.4)
- Stakeholders: Identify Stakeholders (13.1); Plan Stakeholder Engagement (13.2); Plan
  Communications Management (10.1); Manage Stakeholder Engagement (13.3); Manage
  Communications (10.2); Monitor Communications (10.3); Monitor Stakeholder Engagement (13.4)
- Resources: Plan Resource Management (9.1); Estimate Resources (9.2); Acquire Resources
  (9.3); Lead the Team (9.4, 9.5); Monitor and Control Resourcing (9.6)
- Risk: Plan Risk Management (11.1); Identify Risks (11.2); Perform Risk Analysis
  (11.3, 11.4); Plan Risk Responses (11.5); Implement Risk Responses (11.6); Monitor Risks
  (11.7)
