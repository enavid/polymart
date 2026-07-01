"use client";

import { useMutation } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { useState, type ChangeEvent } from "react";

import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { downloadProductsCsv, importProductsCsv } from "@/lib/api/catalog";
import { ApiError } from "@/lib/api/client";

export function ImportExport() {
  const t = useTranslations("catalog");
  const tCommon = useTranslations("common");
  const [file, setFile] = useState<File | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const importMutation = useMutation({
    mutationFn: () => importProductsCsv(file as File),
  });

  async function onExport() {
    setExportError(null);
    try {
      await downloadProductsCsv();
    } catch (error) {
      setExportError(
        error instanceof ApiError ? error.detail : tCommon("genericError"),
      );
    }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
  }

  const result = importMutation.data;

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("importExport.title")}</h1>

      <Card>
        <CardHeader>
          <CardTitle>{t("importExport.exportTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {t("importExport.exportHint")}
          </p>
          <div>
            <Button onClick={onExport}>{t("importExport.exportCta")}</Button>
          </div>
          {exportError ? (
            <Alert variant="destructive">{exportError}</Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("importExport.importTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <p className="text-sm text-muted-foreground">
            {t("importExport.importHint")}
          </p>
          <div className="flex flex-col gap-2">
            <Label htmlFor="import-file">{t("importExport.chooseFile")}</Label>
            <input
              id="import-file"
              type="file"
              accept=".csv"
              onChange={onFileChange}
              className="text-sm"
            />
          </div>
          <div>
            <Button
              onClick={() => importMutation.mutate()}
              disabled={!file || importMutation.isPending}
            >
              {importMutation.isPending
                ? tCommon("loading")
                : t("importExport.importCta")}
            </Button>
          </div>

          {importMutation.isError ? (
            <Alert variant="destructive">
              {importMutation.error instanceof ApiError
                ? importMutation.error.detail
                : tCommon("genericError")}
            </Alert>
          ) : null}

          {result && result.errors.length === 0 ? (
            <Alert variant="success">
              {t("importExport.createdCount", { count: result.created })}
            </Alert>
          ) : null}

          {result && result.errors.length > 0 ? (
            <div className="flex flex-col gap-2">
              <h2 className="text-sm font-medium">
                {t("importExport.rowErrors")}
              </h2>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("importExport.row")}</TableHead>
                    <TableHead>{t("code")}</TableHead>
                    <TableHead>{t("importExport.rowError")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.errors.map((rowError, index) => (
                    <TableRow key={index}>
                      <TableCell>
                        {rowError.row_number === 0
                          ? t("importExport.wholeFile")
                          : rowError.row_number}
                      </TableCell>
                      <TableCell>{rowError.code}</TableCell>
                      <TableCell>{rowError.error}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
