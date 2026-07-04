"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Label } from "@/components/ui/label";
import {
  getCollectionProducts,
  getCollectionRule,
  getCollectionRuleMembers,
  RULE_OPERATORS,
  setCollectionProducts,
  setCollectionRule,
  type RuleCondition,
  type RuleOperator,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

function useMutationError(mutation: {
  error: unknown;
  isError: boolean;
}): string | null {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  if (mutation.error instanceof ApiError) {
    return mutation.error.status === 409
      ? t("alreadyExists")
      : mutation.error.status === 400
        ? t("invalidInput")
        : mutation.error.status === 403
          ? t("forbidden")
          : mutation.error.detail;
  }
  if (mutation.isError) {
    return tCommon("genericError");
  }
  return null;
}

function MembersCard({ slug }: { slug: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["collection-products", slug],
    queryFn: () => getCollectionProducts(slug),
  });

  const [members, setMembers] = useState("");

  useEffect(() => {
    if (query.data) {
      setMembers(query.data.join(", "));
    }
  }, [query.data]);

  const mutation = useMutation({
    mutationFn: () =>
      setCollectionProducts(
        slug,
        members
          .split(",")
          .map((code) => code.trim())
          .filter((code) => code.length > 0),
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collection-products", slug] });
    },
  });

  const error = useMutationError(mutation);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("collectionDetail.members")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {query.isLoading ? <p>{tCommon("loading")}</p> : null}
        <FormField
          id="collection_members"
          label={t("collectionDetail.members")}
          hint={t("collectionDetail.membersHint")}
          value={members}
          onChange={(e) => setMembers(e.target.value)}
        />
        {mutation.isSuccess ? (
          <Alert variant="success">{t("saved")}</Alert>
        ) : null}
        {error ? <Alert variant="destructive">{error}</Alert> : null}
        <div>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("collectionDetail.saveMembers")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function RuleCard({ slug }: { slug: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: ["collection-rule", slug],
    queryFn: () => getCollectionRule(slug),
  });

  const [conditions, setConditions] = useState<RuleCondition[]>([]);

  useEffect(() => {
    if (query.data) {
      setConditions(query.data);
    }
  }, [query.data]);

  const operatorLabels: Record<RuleOperator, string> = {
    equals: t("collectionDetail.opEquals"),
    not_equals: t("collectionDetail.opNotEquals"),
  };

  function updateCondition(index: number, patch: Partial<RuleCondition>) {
    setConditions((current) =>
      current.map((condition, i) => (i === index ? { ...condition, ...patch } : condition)),
    );
  }

  function addCondition() {
    setConditions((current) => [
      ...current,
      { attribute: "", operator: "equals", value: "" },
    ]);
  }

  function removeCondition(index: number) {
    setConditions((current) => current.filter((_, i) => i !== index));
  }

  const mutation = useMutation({
    mutationFn: () => setCollectionRule(slug, conditions),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["collection-rule", slug] });
    },
  });

  const error = useMutationError(mutation);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("collectionDetail.rule")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-xs text-muted-foreground">{t("collectionDetail.ruleHint")}</p>
        {query.isLoading ? <p>{tCommon("loading")}</p> : null}

        {conditions.length === 0 ? (
          <p className="text-muted-foreground">{t("collectionDetail.noConditions")}</p>
        ) : null}

        {conditions.map((condition, index) => (
          <div key={index} className="grid gap-4 md:grid-cols-4 md:items-end">
            <FormField
              id={`condition_attribute_${index}`}
              label={t("collectionDetail.attribute")}
              value={condition.attribute}
              onChange={(e) => updateCondition(index, { attribute: e.target.value })}
            />
            <div className="flex flex-col gap-1.5">
              <Label htmlFor={`condition_operator_${index}`}>
                {t("collectionDetail.operator")}
              </Label>
              <select
                id={`condition_operator_${index}`}
                className="h-10 rounded-md border border-input bg-background px-3 text-sm"
                value={condition.operator}
                onChange={(e) =>
                  updateCondition(index, { operator: e.target.value as RuleOperator })
                }
              >
                {RULE_OPERATORS.map((operator) => (
                  <option key={operator} value={operator}>
                    {operatorLabels[operator]}
                  </option>
                ))}
              </select>
            </div>
            <FormField
              id={`condition_value_${index}`}
              label={t("collectionDetail.value")}
              value={condition.value}
              onChange={(e) => updateCondition(index, { value: e.target.value })}
            />
            <div>
              <Button variant="ghost" onClick={() => removeCondition(index)}>
                {t("remove")}
              </Button>
            </div>
          </div>
        ))}

        <div>
          <Button variant="outline" onClick={addCondition}>
            {t("collectionDetail.addCondition")}
          </Button>
        </div>

        {mutation.isSuccess ? (
          <Alert variant="success">{t("saved")}</Alert>
        ) : null}
        {error ? <Alert variant="destructive">{error}</Alert> : null}
        <div>
          <Button onClick={() => mutation.mutate()} disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("collectionDetail.saveRule")}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function RuleMembersCard({ slug }: { slug: string }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");

  const query = useQuery({
    queryKey: ["collection-rule-members", slug],
    queryFn: () => getCollectionRuleMembers(slug),
    enabled: false,
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("collectionDetail.ruleMembers")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div>
          <Button
            variant="outline"
            onClick={() => void query.refetch()}
            disabled={query.isFetching}
          >
            {query.isFetching
              ? tCommon("loading")
              : t("collectionDetail.refreshMembers")}
          </Button>
        </div>

        {query.isError ? (
          <Alert variant="destructive">
            {query.error instanceof ApiError
              ? query.error.detail
              : tCommon("genericError")}
          </Alert>
        ) : null}

        {query.data && query.data.length === 0 ? (
          <p className="text-muted-foreground">{t("empty")}</p>
        ) : null}

        {query.data && query.data.length > 0 ? (
          <ul className="flex flex-col gap-1 text-sm">
            {query.data.map((code) => (
              <li key={code}>{code}</li>
            ))}
          </ul>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function CollectionDetail({ slug }: { slug: string }) {
  const t = useTranslations("catalog");

  return (
    <div className="flex flex-col gap-6">
      <div>
        <Link
          href="/manage/catalog/collections"
          className="text-sm text-primary hover:underline"
        >
          {t("collectionDetail.backToCollections")}
        </Link>
      </div>
      <h1 className="text-xl font-semibold">{slug}</h1>

      <MembersCard slug={slug} />
      <RuleCard slug={slug} />
      <RuleMembersCard slug={slug} />
    </div>
  );
}
