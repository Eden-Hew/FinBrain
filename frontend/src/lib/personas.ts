import type { Role } from "../api/client";

export interface Persona {
  role: Role;
  label: string;
  description: string;
  capabilities: {
    viewRecommendations: boolean;
    analyzeProcesses: boolean;
    decideRecommendations: boolean;
    viewAudit: boolean;
    manageEinvoiceReadiness: boolean;
    approveEinvoiceSubmission: boolean;
  };
}

export const PERSONAS: Record<Role, Persona> = {
  general_employee: {
    role: "general_employee",
    label: "General employee",
    description: "Basic protected knowledge access; sensitive amounts remain banded.",
    capabilities: {
      viewRecommendations: false,
      analyzeProcesses: false,
      decideRecommendations: false,
      viewAudit: false,
      manageEinvoiceReadiness: false,
      approveEinvoiceSubmission: false,
    },
  },
  finance_ops: {
    role: "finance_ops",
    label: "Finance operator",
    description: "Finance disclosures and recommendation visibility; no approval authority.",
    capabilities: {
      viewRecommendations: true,
      analyzeProcesses: false,
      decideRecommendations: false,
      viewAudit: false,
      manageEinvoiceReadiness: true,
      approveEinvoiceSubmission: false,
    },
  },
  compliance: {
    role: "compliance",
    label: "Compliance reviewer",
    description: "Disclosure and workflow audit access; no recommendation decisions.",
    capabilities: {
      viewRecommendations: true,
      analyzeProcesses: false,
      decideRecommendations: false,
      viewAudit: true,
      manageEinvoiceReadiness: false,
      approveEinvoiceSubmission: false,
    },
  },
  owner_director: {
    role: "owner_director",
    label: "Owner / director",
    description: "Process analysis and recommendation decision authority.",
    capabilities: {
      viewRecommendations: true,
      analyzeProcesses: true,
      decideRecommendations: true,
      viewAudit: false,
      manageEinvoiceReadiness: true,
      approveEinvoiceSubmission: true,
    },
  },
};

export const PERSONA_LIST = Object.values(PERSONAS);
