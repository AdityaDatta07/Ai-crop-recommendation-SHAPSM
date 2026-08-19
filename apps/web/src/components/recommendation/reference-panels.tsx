'use client';

import { useQuery } from '@tanstack/react-query';
import {
  ExternalLink,
  Info,
  Landmark,
  FileText,
  IndianRupee,
  Store,
  ShoppingCart,
  Tractor,
  Handshake,
  ShieldCheck,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { api } from '@/lib/client';
import { useI18n } from '@/i18n/provider';
import { useCropName } from '@/i18n/use-crop-name';
import {
  BUYER_LINKS,
  CREDIT_APPLY_LINKS,
  EMANDI_LINKS,
  INPUT_LINKS,
  PSL_LINKS,
  RENTAL_LINKS,
  SCHEME_LINKS,
  type ReferenceLink,
} from '@/lib/reference-links';
import type { MspResponse } from '@/types/api';

/**
 * Three reference tabs: MSP, farm credit, and government schemes.
 *
 * NONE OF THIS IS COMPUTED, AND THAT IS THE POINT
 * -----------------------------------------------
 * Everything else in this app derives a number from satellite readings, soil
 * models and mandi prices, and every derived number carries a caveat about how
 * far to trust it. These three tabs derive nothing. They restate what the
 * Government of India and the RBI have published, and hand the reader the link.
 *
 * That difference is worth keeping visible. A farmer should be able to tell at
 * a glance which parts of this app are our estimate and which parts are the
 * official position, so these panels lead with their source rather than
 * burying it in a footnote.
 *
 * WHY NO RATES, LIMITS OR ELIGIBILITY
 * -----------------------------------
 * They change by bank, state and year. A stale interest rate presented as
 * current is the same class of error as a fabricated MSP, and it would also
 * contradict the chat, which refuses loan questions three tabs away.
 */

// ------------------------------------------------------------------- MSP

const GROUP_ORDER = ['cereals', 'pulses', 'oilseeds', 'commercial'] as const;

export function MspPanel() {
  const { t, locale } = useI18n();
  const cropName = useCropName();
  const { data, isLoading, isError } = useQuery({
    queryKey: ['msp'],
    queryFn: () => api.getMsp(),
    // Reference data that changes twice a year. Refetching it is pure waste.
    staleTime: Infinity,
  });

  if (isLoading) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">{t('msp.loading')}</CardContent>
      </Card>
    );
  }
  if (isError || !data) {
    return (
      <Card>
        <CardContent className="p-5 text-sm text-muted-foreground">
          {t('msp.unavailable')}
        </CardContent>
      </Card>
    );
  }

  const table = data as MspResponse;
  const money = new Intl.NumberFormat('en-IN');

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IndianRupee className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('msp.heading')}
        </CardTitle>
        <CardDescription>{t('msp.season', { season: table.marketing_season })}</CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t('msp.what')}</p>

        {/* The single most important sentence on this tab. A farmer who reads
            MSP as "what I will be paid" has misread it, and that misreading
            costs money at the mandi gate. */}
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('msp.notGuarantee')}
        </p>

        {GROUP_ORDER.map((group) => {
          const rows = table.crops.filter((crop) => crop.group === group);
          if (rows.length === 0) return null;
          return (
            <section key={group} className="space-y-2">
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                {t(`msp.group${group.charAt(0).toUpperCase()}${group.slice(1)}`)}
              </h3>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border text-left text-xs uppercase tracking-wide text-muted-foreground">
                      <th className="py-2 pr-3 font-medium">{t('msp.colCrop')}</th>
                      <th className="py-2 pr-3 text-right font-medium">{t('msp.colMsp')}</th>
                      <th className="py-2 pr-3 text-right font-medium">{t('msp.colCost')}</th>
                      <th className="py-2 font-medium">{t('msp.colSeason')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((crop) => (
                      <tr key={crop.name} className="border-b border-border/60 last:border-0">
                        <td className="py-2 pr-3">
                          <span className="font-medium">
                            {/* Crops this app ranks resolve through the shared
                                crop-name map, so the MSP table and the ranked
                                list can never show two different names for one
                                crop. The rest fall back to msp.yaml, which
                                carries English and Hindi only. */}
                            {crop.crop_code
                              ? cropName(crop.crop_code, crop.name)
                              : locale === 'hi' && crop.name_hi
                                ? crop.name_hi
                                : crop.name}
                          </span>
                          {/* Marks the crops this app actually ranks, so the
                              two halves of the site visibly connect. */}
                          {crop.crop_code && (
                            <Badge variant="outline" className="ml-2 align-middle text-[10px]">
                              {t('msp.modelled')}
                            </Badge>
                          )}
                        </td>
                        <td className="py-2 pr-3 text-right font-semibold tabular-nums">
                          ₹{money.format(crop.msp_per_quintal)}
                        </td>
                        <td className="py-2 pr-3 text-right tabular-nums text-muted-foreground">
                          {crop.cost_a2fl_per_quintal === null
                            ? '—'
                            : `₹${money.format(crop.cost_a2fl_per_quintal)}`}
                        </td>
                        <td className="py-2 text-muted-foreground">{t(`msp.${crop.season}`)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })}

        <p className="text-xs text-muted-foreground">{t('msp.costNote')}</p>

        {table.not_listed_here.length > 0 && (
          <div className="rounded-md border border-border p-3">
            <p className="text-xs text-muted-foreground">{t('msp.notListed')}</p>
            <ul className="mt-2 space-y-1 text-sm">
              {table.not_listed_here.map((crop) => (
                <li key={crop.name}>
                  <span className="font-medium">
                    {locale === 'hi' && crop.name_hi ? crop.name_hi : crop.name}
                  </span>
                  {crop.note && <span className="text-muted-foreground"> — {crop.note}</span>}
                </li>
              ))}
            </ul>
          </div>
        )}

        <section className="space-y-1.5 border-t border-border pt-3">
          <h3 className="text-sm font-semibold">{t('msp.sourceHeading')}</h3>
          {Object.values(table.sources).map((source) => (
            <a
              key={source.key}
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-start gap-1.5 text-sm text-emerald-800 hover:underline"
            >
              <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden />
              <span>
                {source.title} — {source.publisher}, {source.published}
              </span>
            </a>
          ))}
        </section>
      </CardContent>
    </Card>
  );
}

// ------------------------------------------------------------ link panels

function LinkList({
  links,
  group,
}: {
  links: ReferenceLink[];
  group: 'psl' | 'schemes' | 'emandi' | 'inputs' | 'rental' | 'buyers' | 'credit';
}) {
  const { t } = useI18n();
  return (
    <ul className="space-y-2">
      {links.map((link) => (
        <li key={link.key} className="rounded-lg border border-border p-3">
          <a
            href={link.url}
            target="_blank"
            // noreferrer as well as noopener: these are government sites and
            // there is no reason to hand them the referring URL, which on this
            // app is a capability token for somebody's advisory.
            rel="noopener noreferrer"
            className="flex items-center gap-1.5 font-medium text-emerald-800 hover:underline"
          >
            {t(`${group}.items.${link.key}`).split('—')[0].trim()}
            <ExternalLink className="h-3.5 w-3.5 shrink-0" aria-hidden />
          </a>
          <p className="mt-1 text-sm text-muted-foreground">{t(`${group}.items.${link.key}`)}</p>
          <p className="mt-1 text-xs text-muted-foreground">{link.authority}</p>
        </li>
      ))}
    </ul>
  );
}

export function PslPanel() {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Landmark className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('psl.heading')}
        </CardTitle>
        <CardDescription>{t('psl.what')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('psl.noRates')}
        </p>
        <LinkList links={PSL_LINKS} group="psl" />
        <p className="text-xs text-muted-foreground">{t('psl.disclaimer')}</p>
      </CardContent>
    </Card>
  );
}

export function SchemesPanel() {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <FileText className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('schemes.heading')}
        </CardTitle>
        <CardDescription>{t('schemes.what')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <LinkList links={SCHEME_LINKS} group="schemes" />
        <p className="text-xs text-muted-foreground">{t('schemes.disclaimer')}</p>
      </CardContent>
    </Card>
  );
}

export function EmandiPanel() {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Store className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('emandi.heading')}
        </CardTitle>
        <CardDescription>{t('emandi.what')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Says why the list is short. A farmer who knows three buyer apps and
            sees none of them here should understand that as a rule we follow,
            not as a list we forgot to finish. */}
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('emandi.onlyOfficial')}
        </p>
        <LinkList links={EMANDI_LINKS} group="emandi" />
        <p className="text-xs text-muted-foreground">{t('emandi.disclaimer')}</p>
      </CardContent>
    </Card>
  );
}

// --------------------------------------------------- inputs / rent / buyers

/** One shape for the three "here is where others do this" tabs. */
function LinkTab({
  group,
  icon: Icon,
  links,
  noticeKey,
}: {
  group: 'inputs' | 'rental' | 'buyers';
  icon: typeof Store;
  links: ReferenceLink[];
  noticeKey: string;
}) {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Icon className="h-5 w-5 text-emerald-700" aria-hidden />
          {t(`${group}.heading`)}
        </CardTitle>
        <CardDescription>{t(`${group}.what`)}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Each of these three states plainly what Beej Nirnay is NOT doing:
            not selling, not brokering, not a party to the deal. A farmer
            reading a page of links on a site that also gives them advice will
            otherwise assume we stand behind the transaction. */}
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t(noticeKey)}
        </p>
        <LinkList links={links} group={group} />
        <p className="text-xs text-muted-foreground">{t(`${group}.disclaimer`)}</p>
      </CardContent>
    </Card>
  );
}

export function InputsPanel() {
  return (
    <LinkTab
      group="inputs"
      icon={ShoppingCart}
      links={INPUT_LINKS}
      noticeKey="inputs.neverSell"
    />
  );
}

export function RentalPanel() {
  return <LinkTab group="rental" icon={Tractor} links={RENTAL_LINKS} noticeKey="rental.notParty" />;
}

export function BuyersPanel() {
  return (
    <LinkTab group="buyers" icon={Handshake} links={BUYER_LINKS} noticeKey="buyers.officialOnly" />
  );
}

/**
 * How to apply for a crop loan — appended to the Farm credit tab.
 *
 * Not a separate tab, because two tabs about borrowing invites the reader to
 * treat one of them as the "real" one. Not an eligibility check either: this
 * lists what to carry and where to go, and says outright that only a bank can
 * tell you whether you qualify. Assessing that here would make this a
 * regulated intermediary and would put a wrong answer between a farmer and
 * their creditworthiness.
 */
export function CreditApplySection() {
  const { t } = useI18n();
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ShieldCheck className="h-5 w-5 text-emerald-700" aria-hidden />
          {t('credit.applyHeading')}
        </CardTitle>
        <CardDescription>{t('credit.applyWhat')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
          {t('credit.notAssessing')}
        </p>

        <section className="space-y-1.5">
          <h3 className="text-sm font-semibold">{t('credit.documentsHeading')}</h3>
          <p className="text-sm text-muted-foreground">{t('credit.documents')}</p>
        </section>

        {/* Worth its own box. Tenant farmers are routinely turned away from
            credit they are entitled to, and the reason is usually that nobody
            told them the Joint Liability Group route exists. */}
        <p className="rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-900">
          {t('credit.tenantNote')}
        </p>

        <LinkList links={CREDIT_APPLY_LINKS} group="credit" />
      </CardContent>
    </Card>
  );
}
