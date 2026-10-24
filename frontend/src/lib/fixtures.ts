/**
 * Mock API responses used during frontend development before the backend is
 * wired. Shapes come from the shared contracts so fixtures can't drift.
 */
import type {
  AnalyzeResponse,
  ExtractResponse,
  LetterResponse,
  ProceduresResponse,
} from '@contracts';

export const fixtureExtract: ExtractResponse = {
  line_items: [
    {
      code: '99214',
      description: 'Office visit, established patient (moderate complexity)',
      units: 1,
      charge: 32000,
      confidence: 0.94,
      needs_confirmation: false,
    },
    {
      code: '80053',
      description: 'Comprehensive metabolic blood panel',
      units: 1,
      charge: 8800,
      confidence: 0.71,
      needs_confirmation: true,
    },
    {
      code: '71046',
      description: 'Chest X-ray (two views)',
      units: 1,
      charge: 21000,
      confidence: 0.88,
      needs_confirmation: false,
    },
  ],
  overall_confidence: 0.84,
};

export const fixtureAnalyze: AnalyzeResponse = {
  results: [
    {
      line_index: 0,
      plain_language_label: 'Office visit, established patient (moderate complexity)',
      medicare_reference: 13100,
      ma_price_range: { low: 16000, high: 32000, source: 'sample' },
      flags: [],
    },
    {
      line_index: 1,
      plain_language_label: 'Comprehensive metabolic blood panel',
      medicare_reference: 1400,
      ma_price_range: { low: 2500, high: 9000, source: 'sample' },
      flags: [],
    },
    {
      line_index: 2,
      plain_language_label: 'Chest X-ray (two views)',
      medicare_reference: 2800,
      ma_price_range: { low: 4000, high: 18000, source: 'sample' },
      flags: [
        {
          explanation:
            'This charge is above the typical Massachusetts range we have for this service. Confirming it with the provider can help.',
          basis: 'ma_price_range',
        },
      ],
    },
  ],
};

export const fixtureProcedures: ProceduresResponse = {
  procedures: [
    {
      code: '99213',
      plain_language_label: 'Office visit, established patient (low complexity)',
      description: 'Outpatient office or other visit, established patient, ~15 min.',
      medicare_reference: 9200,
      ma_price_range: { low: 11000, high: 24000, source: 'sample' },
    },
    {
      code: '80053',
      plain_language_label: 'Comprehensive metabolic blood panel',
      description: 'A group of blood tests measuring chemistry/organ function.',
      medicare_reference: 1400,
      ma_price_range: { low: 2500, high: 9000, source: 'sample' },
    },
  ],
};

export const fixtureLetter: LetterResponse = {
  letter: {
    type: 'itemized_bill_request',
    recipient: 'provider',
    subject: 'Request for an itemized bill',
    body:
      'Dear [Provider Billing Office],\n\n' +
      'My name is [Your Name] and my account number is [Account Number]. ' +
      'I recently received a bill dated [Date] and would like to better understand the charges. ' +
      'Could you please send me a fully itemized bill that lists each service, its billing code, and the amount charged?\n\n' +
      'Thank you for your help. You can reach me at [Phone or Email].\n\n' +
      'Sincerely,\n[Your Name]',
  },
};
