"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

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
import { Loading } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createCategory,
  listCategories,
  type Category,
} from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const CATEGORIES_KEY = "catalog-categories";

function CreateCategoryForm({
  categories,
  onCreated,
}: {
  categories: Category[];
  onCreated: () => void;
}) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [parent, setParent] = useState("");

  const mutation = useMutation({
    mutationFn: () => createCategory({ slug, name, parent: parent || null }),
    onSuccess: () => {
      setSlug("");
      setName("");
      setParent("");
      onCreated();
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
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
        <CardTitle>{t("categories.createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-3" noValidate>
          <FormField
            id="category_slug"
            label={t("slug")}
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          />
          <FormField
            id="category_name"
            label={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="category_parent">{t("categories.parent")}</Label>
            <select
              id="category_parent"
              name="category_parent"
              value={parent}
              onChange={(e) => setParent(e.target.value)}
              className="h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              <option value="">{t("categories.parentNone")}</option>
              {categories.map((category) => (
                <option key={category.slug} value={category.slug}>
                  {category.slug}
                </option>
              ))}
            </select>
          </div>
          {mutation.isSuccess ? (
            <Alert variant="success" className="md:col-span-3">
              {t("created")}
            </Alert>
          ) : null}
          {error ? (
            <Alert variant="destructive" className="md:col-span-3">
              {error}
            </Alert>
          ) : null}
          <div className="md:col-span-3">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("create")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

export function CategoriesManager() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [CATEGORIES_KEY],
    queryFn: listCategories,
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [CATEGORIES_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("categories.title")}</h1>

      <CreateCategoryForm categories={query.data ?? []} onCreated={refreshList} />

      {query.isLoading ? <Loading label={tCommon("loading")} /> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("categories.empty")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("slug")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead>{t("categories.parent")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((category) => (
              <TableRow key={category.slug}>
                <TableCell className="font-medium">{category.slug}</TableCell>
                <TableCell>{category.name}</TableCell>
                <TableCell>{category.parent ?? t("none")}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
