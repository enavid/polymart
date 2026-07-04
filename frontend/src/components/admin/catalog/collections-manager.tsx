"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
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
import { Loading } from "@/components/ui/spinner";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { createCollection, listCollections } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

const COLLECTIONS_KEY = "catalog-collections";

function CreateCollectionForm({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");

  const mutation = useMutation({
    mutationFn: () => createCollection({ slug, name }),
    onSuccess: () => {
      setSlug("");
      setName("");
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
        <CardTitle>{t("collections.createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-2" noValidate>
          <FormField
            id="collection_slug"
            label={t("slug")}
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          />
          <FormField
            id="collection_name"
            label={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
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

export function CollectionsManager() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();

  const query = useQuery({
    queryKey: [COLLECTIONS_KEY],
    queryFn: () => listCollections(),
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [COLLECTIONS_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("collections.title")}</h1>

      <CreateCollectionForm onCreated={refreshList} />

      {query.isLoading ? <Loading label={tCommon("loading")} /> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("collections.empty")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("slug")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((collection) => (
              <TableRow key={collection.slug}>
                <TableCell className="font-medium">{collection.slug}</TableCell>
                <TableCell>{collection.name}</TableCell>
                <TableCell>
                  <Link
                    href={`/manage/catalog/collections/${collection.slug}`}
                    className="text-primary hover:underline"
                  >
                    {t("collections.manage")}
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
