/**
 * Official Massachusetts consumer and financial-assistance resources.
 *
 * ⚠️ EVERY link below is marked `verifyBeforeShipping: true`. Before the app is
 * shown to real users, a human MUST confirm each URL is current, official, and
 * points where this description says. Do not ship with unverified links.
 *
 * These are informational references only; the app provides general information.
 */

export interface ResourceLink {
  label: string;
  url: string;
  description: string;
  /** TODO: set to false only after a human verifies the URL is official + current. */
  verifyBeforeShipping: boolean;
}

export const MA_RESOURCES: ResourceLink[] = [
  {
    label: 'Massachusetts Health Policy Commission',
    url: 'https://www.mass.gov/orgs/health-policy-commission',
    description:
      'State agency focused on health care cost and quality in Massachusetts.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
  {
    label: 'Office of Patient Protection (OPP)',
    url: 'https://www.mass.gov/orgs/office-of-patient-protection',
    description:
      'Helps with questions about health plan coverage and the appeals process.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
  {
    label: 'Massachusetts health care consumer resources',
    url: 'https://www.mass.gov/health-care',
    description:
      'Consumer assistance for billing and insurance questions and complaints.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
  {
    label: 'Health Safety Net (HSN)',
    url: 'https://www.mass.gov/health-safety-net',
    description:
      'Program that may help with hospital and community health center bills for eligible residents.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
  {
    label: 'MassHealth',
    url: 'https://www.mass.gov/masshealth',
    description:
      'Massachusetts Medicaid/CHIP program; may help with coverage and costs for those who qualify.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
  {
    label: 'Health Care For All — HelpLine',
    url: 'https://www.hcfama.org/helpline',
    description:
      'Nonprofit helpline that offers free help understanding coverage and bills.',
    verifyBeforeShipping: true, // TODO verify before shipping
  },
];
