"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Alert } from "@/components/ui/alert";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ApiError } from "@/lib/api/client";
import { getWallet, type WalletTransaction } from "@/lib/api/wallet";
import { formatJalaliDateTime, formatMoneyString } from "@/lib/format";

export const WALLET_KEY = ["wallet"] as const;

/** Map a ledger entry's reason to a localized label key (falls back to the raw reason). */
const REASON_KEYS: Record<string, string> = {
  refund: "reasonRefund",
  adjustment: "reasonAdjustment",
};

/**
 * The signed-in user's wallet: current balance and recent statement.
 *
 * The balance is the server's exact string, rendered (not recomputed) in Toman for the
 * Iranian market. A user who has never received store credit reads an empty wallet (zero
 * balance, no entries) rather than an error.
 */
export function WalletView() {
  const t = useTranslations("wallet");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: WALLET_KEY,
    queryFn: () => getWallet(),
  });

  const wallet = query.data;

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col gap-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <h1 className="text-2xl font-bold tracking-tight">{t("title")}</h1>
        <Link href="/account" className="text-sm text-primary hover:underline">
          {t("backToAccount")}
        </Link>
      </header>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError ? query.error.detail : t("loadError")}
        </Alert>
      ) : null}

      {wallet ? (
        <>
          <Card>
            <CardHeader>
              <CardTitle>{t("balanceTitle")}</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-3xl font-bold" data-testid="wallet-balance">
                {formatMoneyString(wallet.balance, wallet.currency)}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">{t("balanceHint")}</p>
            </CardContent>
          </Card>

          <section className="flex flex-col gap-3">
            <h2 className="text-lg font-semibold">{t("statementTitle")}</h2>
            {wallet.transactions.length === 0 ? (
              <p className="text-muted-foreground">{t("empty")}</p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("date")}</TableHead>
                    <TableHead>{t("reason")}</TableHead>
                    <TableHead>{t("amount")}</TableHead>
                    <TableHead>{t("balanceAfter")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {wallet.transactions.map((txn) => (
                    <TransactionRow key={`${txn.created_at}-${txn.source_reference}`} txn={txn} />
                  ))}
                </TableBody>
              </Table>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}

function TransactionRow({ txn }: { txn: WalletTransaction }) {
  const t = useTranslations("wallet");
  const reasonKey = REASON_KEYS[txn.reason];
  // A credit adds value (shown with a leading +); a debit removes it (leading −).
  const sign = txn.type === "credit" ? "+" : "−";
  return (
    <TableRow>
      <TableCell>{formatJalaliDateTime(txn.created_at)}</TableCell>
      <TableCell>{reasonKey ? t(reasonKey) : txn.reason}</TableCell>
      <TableCell
        className={txn.type === "credit" ? "text-emerald-600" : "text-destructive"}
      >
        {sign} {formatMoneyString(txn.amount, txn.currency)}
      </TableCell>
      <TableCell>{formatMoneyString(txn.balance_after, txn.currency)}</TableCell>
    </TableRow>
  );
}
