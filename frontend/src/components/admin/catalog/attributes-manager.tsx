"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
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
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ATTRIBUTE_INPUT_TYPES,
  createAttribute,
  listAttributes,
  type AttributeChoice,
  type AttributeInputType,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const ATTRIBUTES_KEY = "catalog-attributes";

function CreateAttributeForm({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [inputType, setInputType] = useState<AttributeInputType>("plain_text");
  const [required, setRequired] = useState(false);
  const [choices, setChoices] = useState<AttributeChoice[]>([]);

  const inputTypeLabels: Record<AttributeInputType, string> = {
    plain_text: t("attributes.typePlainText"),
    number: t("attributes.typeNumber"),
    boolean: t("attributes.typeBoolean"),
    dropdown: t("attributes.typeDropdown"),
  };

  const mutation = useMutation({
    mutationFn: () =>
      createAttribute({
        code,
        name,
        input_type: inputType,
        required,
        choices,
      }),
    onSuccess: () => {
      setCode("");
      setName("");
      setInputType("plain_text");
      setRequired(false);
      setChoices([]);
      onCreated();
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  function addChoice() {
    setChoices((prev) => [...prev, { value: "", label: "" }]);
  }

  function updateChoice(index: number, patch: Partial<AttributeChoice>) {
    setChoices((prev) =>
      prev.map((choice, i) => (i === index ? { ...choice, ...patch } : choice)),
    );
  }

  function removeChoice(index: number) {
    setChoices((prev) => prev.filter((_, i) => i !== index));
  }

  let error: string | null = null;
  if (mutation.error instanceof ApiError) {
    error =
      mutation.error.status === 409
        ? t("alreadyExists")
        : mutation.error.status === 400
          ? t("invalidInput")
          : mutation.error.status === 403
            ? t("forbidden")
            : mutation.error.detail;
  } else if (mutation.isError) {
    error = tCommon("genericError");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("attributes.createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2" noValidate>
          <FormField
            id="attribute_code"
            label={t("code")}
            value={code}
            onChange={(e) => setCode(e.target.value)}
            required
          />
          <FormField
            id="attribute_name"
            label={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="attribute_input_type">{t("attributes.inputType")}</Label>
            <select
              id="attribute_input_type"
              name="attribute_input_type"
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
              value={inputType}
              onChange={(e) => setInputType(e.target.value as AttributeInputType)}
            >
              {ATTRIBUTE_INPUT_TYPES.map((type) => (
                <option key={type} value={type}>
                  {inputTypeLabels[type]}
                </option>
              ))}
            </select>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={required}
              onChange={(e) => setRequired(e.target.checked)}
            />
            {t("attributes.required")}
          </label>

          <div className="flex flex-col gap-3 md:col-span-2">
            <p className="text-sm font-medium">{t("attributes.choices")}</p>
            {choices.map((choice, index) => (
              <div key={index} className="grid gap-4 md:grid-cols-[1fr_1fr_auto] md:items-end">
                <FormField
                  id={`attribute_choice_value_${index}`}
                  label={t("attributes.choiceValue")}
                  value={choice.value}
                  onChange={(e) => updateChoice(index, { value: e.target.value })}
                />
                <FormField
                  id={`attribute_choice_label_${index}`}
                  label={t("attributes.choiceLabel")}
                  value={choice.label}
                  onChange={(e) => updateChoice(index, { label: e.target.value })}
                />
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => removeChoice(index)}
                >
                  {t("remove")}
                </Button>
              </div>
            ))}
            <div>
              <Button type="button" variant="outline" onClick={addChoice}>
                {t("attributes.addChoice")}
              </Button>
            </div>
          </div>

          {mutation.isSuccess ? (
            <Alert variant="success" className="md:col-span-2">
              {t("created")}
            </Alert>
          ) : null}
          {error ? (
            <Alert variant="destructive" className="md:col-span-2">
              {error}
            </Alert>
          ) : null}
          <div className="md:col-span-2">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("create")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function AttributesManager() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [ATTRIBUTES_KEY],
    queryFn: listAttributes,
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [ATTRIBUTES_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("attributes.title")}</h1>

      <CreateAttributeForm onCreated={refreshList} />

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("attributes.empty")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("code")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead>{t("attributes.inputType")}</TableHead>
              <TableHead>{t("attributes.required")}</TableHead>
              <TableHead>{t("attributes.choices")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((attribute) => (
              <TableRow key={attribute.code}>
                <TableCell className="font-medium">{attribute.code}</TableCell>
                <TableCell>{attribute.name}</TableCell>
                <TableCell>{attribute.input_type}</TableCell>
                <TableCell>
                  <Badge variant={attribute.required ? "active" : "inactive"}>
                    {attribute.required ? t("attributes.required") : t("none")}
                  </Badge>
                </TableCell>
                <TableCell>{attribute.choices.length}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
