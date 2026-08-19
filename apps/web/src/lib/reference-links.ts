/**
 * Curated links to government and RBI pages. No computation, no claims.
 *
 * WHY THE LINKS LIVE HERE AND THE PROSE LIVES IN i18n
 * ---------------------------------------------------
 * A URL is the same in every language; a description is not. Splitting them
 * this way means adding a language never risks a typo'd link, and the
 * dictionary parity test covers the descriptions automatically.
 *
 * WHAT THIS DELIBERATELY DOES NOT DO
 * ----------------------------------
 * It does not state interest rates, loan limits, subsidy amounts or
 * eligibility. Those change by scheme, by bank, by state and by year, and a
 * stale figure on this page would be read as current — the same failure mode
 * as a fabricated MSP. Every entry sends the reader to the authority that
 * publishes the current terms, which is the honest thing a static page can do.
 *
 * Rates and limits are also exactly what the chat refuses to discuss, so
 * quoting them here would contradict the refusal three tabs away.
 */

export interface ReferenceLink {
  /** i18n key under `psl.items.*` or `schemes.items.*`. */
  key: string;
  url: string;
  /** Who publishes it, shown verbatim — it is what makes the link checkable. */
  authority: string;
}

/**
 * Priority Sector Lending — the RBI rule that obliges banks to direct a share
 * of lending to agriculture and other priority sectors.
 */
export const PSL_LINKS: ReferenceLink[] = [
  {
    key: 'masterDirections',
    url: 'https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx',
    authority: 'Reserve Bank of India',
  },
  {
    key: 'kcc',
    url: 'https://www.myscheme.gov.in/schemes/kcc',
    authority: 'Government of India (myScheme)',
  },
  {
    key: 'nabard',
    url: 'https://www.nabard.org/',
    authority: 'NABARD',
  },
  {
    key: 'agriInfra',
    url: 'https://agriinfra.dac.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'jansamarth',
    url: 'https://www.jansamarth.in/',
    authority: 'Government of India',
  },
  {
    key: 'bankList',
    url: 'https://www.rbi.org.in/Scripts/banklinks.aspx',
    authority: 'Reserve Bank of India',
  },
];

/**
 * Electronic mandis and the portals around selling.
 *
 * The rest of this app stops at "what should I grow". A farmer's year does not
 * — the crop still has to be sold, and where it is sold moves the price more
 * than most agronomic decisions do. These are the official routes.
 *
 * Note what is absent: private buyer platforms and aggregators. Several are
 * genuinely useful, but listing some and not others on a page a farmer reads
 * as neutral is an endorsement we have not earned and cannot maintain. Every
 * entry here is government-run or government-backed, which is a rule that can
 * be checked rather than a judgement that has to be defended.
 */
export const EMANDI_LINKS: ReferenceLink[] = [
  // State mandi boards are deliberately absent. Most run on bare .in or .com
  // domains that cannot be verified as official from the URL alone, and one
  // unverified link on a page of official ones lends it the credibility of
  // its neighbours. A farmer is better served by e-NAM and their own state
  // agriculture department than by a link here we cannot vouch for.
  {
    key: 'enam',
    url: 'https://enam.gov.in/web/',
    authority: 'Small Farmers Agribusiness Consortium',
  },
  {
    key: 'enamRegister',
    url: 'https://enam.gov.in/web/registration-form/farmer',
    authority: 'Small Farmers Agribusiness Consortium',
  },
  {
    key: 'agmarknetPrices',
    url: 'https://agmarknet.gov.in/PriceTrends/SA_Pri_Month.aspx',
    authority: 'Directorate of Marketing & Inspection',
  },
  {
    key: 'karnatakaRms',
    url: 'https://rms.karnataka.gov.in/',
    authority: 'Karnataka State Agricultural Marketing Board',
  },
  {
    key: 'fciProcurement',
    url: 'https://fci.gov.in/procurements/',
    authority: 'Food Corporation of India',
  },
];

/** Central schemes a farmer can look up and apply to. */
export const SCHEME_LINKS: ReferenceLink[] = [
  {
    key: 'pmKisan',
    url: 'https://pmkisan.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'pmfby',
    url: 'https://pmfby.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'soilHealth',
    url: 'https://soilhealth.dac.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'kisanCallCentre',
    url: 'https://mkisan.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'myScheme',
    url: 'https://www.myscheme.gov.in/search',
    authority: 'Government of India',
  },
  {
    key: 'kvk',
    url: 'https://kvk.icar.gov.in/',
    authority: 'Indian Council of Agricultural Research',
  },
];

/**
 * Buying inputs — seed, fertiliser, machinery.
 *
 * THIS APP WILL NEVER SELL THESE, AND THAT IS A DESIGN DECISION
 * ------------------------------------------------------------
 * The moment a crop advisory also sells seed, every recommendation it makes
 * becomes suspect: a farmer cannot tell whether chickpea was suggested because
 * the soil suits it or because there is chickpea seed to move. No disclosure
 * fixes that, because the farmer has no way to check.
 *
 * So these are links to where inputs are sold and regulated by others, and
 * Beej Nirnay takes no cut, holds no stock and makes no recommendation about
 * a brand.
 */
export const INPUT_LINKS: ReferenceLink[] = [
  {
    key: 'seedPortal',
    url: 'https://seednet.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'onlineFertiliser',
    url: 'https://dbtfert.nic.in/',
    authority: 'Department of Fertilizers',
  },
  {
    key: 'inputQuality',
    url: 'https://agriwelfare.gov.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
];

/**
 * Renting equipment rather than buying it.
 *
 * Custom Hiring Centres are the government's own answer to the fact that a
 * tractor costs more than most holdings earn in a decade. These are the
 * official directories; the transaction, the dispute and the deposit are
 * between the farmer and the centre, and this app is not a party to any of it.
 */
export const RENTAL_LINKS: ReferenceLink[] = [
  {
    key: 'farmsApp',
    url: 'https://agrimachinery.nic.in/Index/CHC',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'chcDirectory',
    url: 'https://agrimachinery.nic.in/',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'smam',
    url: 'https://agriwelfare.gov.in/en/Major',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
];

/**
 * Finding a buyer beyond the local mandi.
 *
 * Same rule as the e-mandi tab: official and cooperative routes only. Private
 * aggregators are excluded not because they are bad but because choosing
 * between them is an endorsement, and a farmer reading a neutral-looking page
 * would take it as one.
 */
export const BUYER_LINKS: ReferenceLink[] = [
  {
    key: 'fpoPortal',
    url: 'https://sfacindia.com/FPOS.aspx',
    authority: 'Small Farmers Agribusiness Consortium',
  },
  {
    key: 'exportApeda',
    url: 'https://apeda.gov.in/',
    authority: 'APEDA, Ministry of Commerce',
  },
  {
    key: 'gemPortal',
    url: 'https://gem.gov.in/',
    authority: 'Government e-Marketplace',
  },
];

/**
 * Applying for credit — the process, not the assessment.
 *
 * WHAT THIS DELIBERATELY IS NOT
 * -----------------------------
 * It does not check eligibility, score an application, or forward anything to
 * a lender. Doing any of those would make this a regulated intermediary, and
 * getting an eligibility answer wrong costs a farmer their creditworthiness
 * rather than merely their time.
 *
 * What it does is remove the actual obstacle, which is not usually eligibility:
 * it is not knowing which document is missing before walking to the branch.
 */
export const CREDIT_APPLY_LINKS: ReferenceLink[] = [
  {
    key: 'kccApply',
    url: 'https://www.jansamarth.in/kisan-credit-card-scheme',
    authority: 'Government of India',
  },
  {
    key: 'pmKisanKcc',
    url: 'https://pmkisan.gov.in/Documents/KCC.pdf',
    authority: 'Ministry of Agriculture & Farmers Welfare',
  },
  {
    key: 'rbiGrievance',
    url: 'https://cms.rbi.org.in/',
    authority: 'Reserve Bank of India',
  },
  {
    key: 'nabardSchemes',
    url: 'https://www.nabard.org/content.aspx?id=514',
    authority: 'NABARD',
  },
];
