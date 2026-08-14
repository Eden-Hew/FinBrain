# FinBrain: Five-Feature Product Plan

## Purpose

This plan defines the five connected features that will position FinBrain as an industrial customer-intelligence and process-optimization platform rather than a packaged AI chatbot.

FinBrain's core promise is:

> **One customer memory. The right answer for every role. Proof behind every answer.**

The product should unify scattered company knowledge, answer questions using evidence, protect sensitive data, respect access permissions, and turn intelligence into controlled business actions.

## Target Demo Scenario

A user asks:

> **Why is Acme Retail at risk, and what should we do next?**

FinBrain should:

1. Combine relevant information from meetings, Telegram messages, invoices, CRM records, and documents.
2. Produce a structured customer-intelligence brief.
3. Cite the evidence behind every important conclusion.
4. Show that sensitive data was protected before external AI processing.
5. Demonstrate how the answer changes for different user roles.
6. Convert the recommended action into a human approval workflow.
7. Record the disclosure and action in the audit trail.

This creates one continuous story:

```text
Scattered knowledge
    -> evidence-backed intelligence
    -> privacy and permission controls
    -> recommended action
    -> human approval
    -> auditable outcome
```

---

## Feature 1: Customer Intelligence Brief

### Idea

Replace ordinary chatbot paragraphs with a structured decision brief that helps the user understand a customer and decide what to do next.

### Information shown

- Customer health: Healthy, Needs Attention, or At Risk
- Executive summary
- Important recent events
- Open customer commitments
- Financial or operational risks
- Recommended next action
- Supporting evidence
- Missing or uncertain information

### Example

> **Acme Retail — At Risk**
>
> Payment is 24 days overdue. Two delivery complaints remain unresolved, and a replacement approved during the 12 July meeting has no recorded delivery confirmation.
>
> **Recommended action:** Resolve the delivery issue before initiating another collection request.

### Why it matters

This makes FinBrain feel like a customer-intelligence product rather than a general chat interface. The answer is designed for decision-making, not merely reading.

### Success criteria

- A judge understands the customer's situation within ten seconds.
- The brief separates facts, risks, recommendations, and missing information.
- The status is based on visible signals rather than an unexplained AI score.

---

## Feature 2: Clickable Evidence Drawer

### Idea

Every important claim in the intelligence brief should link to the company record that supports it.

### Information shown for each citation

- Source system
- Record type
- Record date
- Relevant protected excerpt
- Information freshness
- Access status
- Relationship to the conclusion

### Evidence labels

- **Supporting:** Confirms the conclusion
- **Contradicting:** Conflicts with another record
- **Stale:** May no longer reflect the current situation
- **Missing:** Required evidence could not be found

### Example

> Delivery problems remain unresolved. **[1][2]**

Selecting citation **[1]** opens:

```text
Source: Telegram
Date: 10 August 2026
Status: Current
Evidence: Customer reported that the replacement had not arrived.
Access: Visible to Finance Director and assigned account team.
```

### Why it matters

Trustworthy enterprise intelligence requires more than a generated answer. Users need to verify where each conclusion came from and notice when company records disagree.

### Success criteria

- Every major claim has at least one citation or is explicitly marked unverified.
- A user can inspect evidence without leaving the answer.
- Conflicting and stale information is visible rather than silently ignored.

---

## Feature 3: AI Exposure Receipt

### Idea

Show exactly what information the external AI received and what FinBrain protected locally.

### Information shown

```text
Sensitive fields detected: 7
Fields protected before AI processing: 7
Raw sensitive values sent externally: 0
Reasoning provider: Gemini
Values restored for this user: 3
Active access policy: Finance Director
Audit reference: FB-8C42A
```

### Three views

1. **What the user asked**
2. **What the AI received**
3. **What FinBrain returned to the user**

Example of the protected AI view:

```text
[CUSTOMER_8F21] has an overdue balance in [AMOUNT_BAND_3].
[PERSON_B112] reported that the replacement delivery is still missing.
```

### Why it matters

Privacy protection normally happens invisibly. The receipt turns FinBrain's technical privacy boundary into a product feature that judges and enterprise buyers can immediately understand.

### Success criteria

- Users can confirm that raw sensitive values were protected before model processing.
- The receipt identifies the model, role, policy, and audit event involved.
- The protected prompt can be demonstrated safely during judging.

---

## Feature 4: Role Comparison View

### Idea

Run the same customer question for different roles and show how permissions affect the sources, details, and final answer.

### Roles demonstrated

- Finance Director
- Employee
- Guest

### Example comparison

| Information | Finance Director | Employee | Guest |
|---|---|---|---|
| Customer identity | Visible | Visible when assigned | Hidden |
| Exact overdue amount | Visible | Hidden | Hidden |
| Operational issue | Visible | Visible | Safe summary only |
| Bank information | Visible only when required | Hidden | Hidden |
| Restricted evidence | Available | Withheld | Withheld |

### Required explanation

Hidden information should not disappear without explanation. FinBrain should state:

> Exact invoice amount withheld because the Employee role does not have access to restricted financial values.

### Why it matters

The track specifically requires respecting who is allowed to see what. A side-by-side comparison makes FinBrain's access controls visually undeniable.

### Success criteria

- The same question produces meaningfully different authorized views.
- Restricted values never appear briefly before being hidden.
- Every withheld field includes a human-readable policy explanation.
- Each allow or deny decision is recorded in the audit trail.

---

## Feature 5: Recommendation-to-Approval Workflow

### Idea

Turn customer intelligence into a proposed business action while keeping a human responsible for the final decision.

### Available actions

- Create a customer follow-up task
- Draft a customer response
- Assign an account owner
- Escalate a service issue
- Request missing information
- Draft a process-improvement rule

### Approval item should include

- Proposed action
- Reason for the recommendation
- Supporting evidence
- Responsible owner
- Priority and deadline
- Sensitive information involved
- Expected outcome
- Approve, edit, and reject controls

### Example

```text
Proposed action:
Resolve the delivery dispute before contacting the customer about payment.

Reason:
The overdue invoice and unresolved delivery complaint appear in the same
customer timeline. The promised replacement has no delivery confirmation.

Owner: Customer Operations
Priority: High
Approval required: Finance Director
```

### Why it matters

Many AI products stop after answering a question. FinBrain should connect knowledge to a controlled operational process with evidence, ownership, approval, and auditing.

### Success criteria

- A recommendation can become an approval item with one click.
- The evidence remains attached throughout the workflow.
- Approving or rejecting the action creates an audit event.
- No external action occurs without human approval during the prototype.

---

## How the Five Features Work Together

The five features should not feel like separate modules. They form one decision workflow:

```text
1. Customer Intelligence Brief
   Understand the customer and proposed next step.

2. Evidence Drawer
   Verify the facts, conflicts, freshness, and missing information.

3. AI Exposure Receipt
   Confirm how sensitive data was protected during AI processing.

4. Role Comparison
   Prove that each person receives only authorized information.

5. Recommendation-to-Approval
   Convert the insight into a controlled and auditable action.
```

## Recommended Demo Script

### Step 1: Establish the problem

Explain that Acme Retail's information is spread across Telegram, meetings, invoices, CRM records, and documents.

### Step 2: Ask the question

> Why is Acme Retail at risk, and what should we do next?

### Step 3: Present the intelligence brief

Show the risk status, important events, unresolved commitment, and recommended action.

### Step 4: Inspect the evidence

Open citations that show the overdue invoice, customer complaint, meeting promise, and missing delivery confirmation.

### Step 5: Prove privacy

Open the AI Exposure Receipt and compare the original information with the protected prompt sent to the model.

### Step 6: Prove authorization

Switch from Finance Director to Employee and Guest. Show restricted fields being withheld with policy explanations.

### Step 7: Create an action

Convert the recommendation into a follow-up or service-resolution request and send it to Approvals.

### Step 8: Approve and audit

Approve the action and show the complete chain in the audit trail.

## Suggested Team Workstreams

### Product and Demo Story

- Finalize the Acme Retail scenario.
- Prepare realistic cross-source sample records.
- Write the presentation and demo script.

### Intelligence Experience

- Build the Customer Intelligence Brief.
- Add evidence citations and the Evidence Drawer.
- Include conflicts, freshness, and missing-information states.

### Privacy and Authorization

- Build the AI Exposure Receipt.
- Create the Role Comparison View.
- Confirm that protected values cannot leak between roles.

### Workflow and Audit

- Connect recommended actions to the Approvals queue.
- Preserve supporting evidence throughout the workflow.
- Record approval, rejection, and disclosure decisions in the audit trail.

## Priority Order

If time is limited, work in this order:

1. Customer Intelligence Brief
2. Clickable Evidence Drawer
3. AI Exposure Receipt
4. Role Comparison View
5. Recommendation-to-Approval Workflow

The first two establish customer intelligence and trust. The next two prove FinBrain's privacy and authorization advantage. The final feature demonstrates process optimization.

## Scope Boundaries

For the hackathon prototype:

- Use one excellent customer scenario rather than many shallow examples.
- Use realistic sample records where live integrations are unavailable.
- Do not claim that simulated integrations are live.
- Do not present customer-health status as a trained prediction unless a real model exists.
- Keep all external actions behind human approval.
- Describe privacy and compliance controls accurately without claiming formal certification.
- Focus on evidence, permissions, and controlled action rather than adding more generic agents.

## Final Product Message

> **FinBrain unifies scattered customer knowledge, produces evidence-backed answers, protects sensitive data before AI processing, adapts every answer to the requester's permissions, and turns intelligence into controlled action.**

The five-feature package gives the team one cohesive industrial story and one memorable end-to-end demonstration.
