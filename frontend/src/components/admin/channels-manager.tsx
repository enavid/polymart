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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  createChannel,
  listChannels,
  setChannelStatus,
  type Channel,
} from "@/lib/api/channels";
import { ApiError } from "@/lib/api/client";

const CHANNELS_KEY = "channels";

function CreateChannelForm({ onCreated }: { onCreated: () => void }) {
  const t = useTranslations("channels");
  const tCommon = useTranslations("common");
  const [slug, setSlug] = useState("");
  const [name, setName] = useState("");
  const [currency, setCurrency] = useState("");

  const mutation = useMutation({
    mutationFn: () => createChannel({ slug, name, currency }),
    onSuccess: () => {
      setSlug("");
      setName("");
      setCurrency("");
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
          : mutation.error.detail;
  } else if (mutation.isError) {
    error = tCommon("genericError");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("createTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="grid gap-4 md:grid-cols-3" noValidate>
          <FormField
            id="channel_slug"
            label={t("slug")}
            value={slug}
            onChange={(e) => setSlug(e.target.value)}
            required
          />
          <FormField
            id="channel_name"
            label={t("name")}
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <FormField
            id="channel_currency"
            label={t("currency")}
            value={currency}
            onChange={(e) => setCurrency(e.target.value.toUpperCase())}
            required
          />
          {mutation.isSuccess ? (
            <Alert variant="success" className="md:col-span-3">
              {t("createSuccess")}
            </Alert>
          ) : null}
          {error ? (
            <Alert variant="destructive" className="md:col-span-3">
              {error}
            </Alert>
          ) : null}
          <div className="md:col-span-3">
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? tCommon("loading") : t("createCta")}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function ChannelRow({ channel }: { channel: Channel }) {
  const t = useTranslations("channels");
  const queryClient = useQueryClient();
  const mutation = useMutation({
    mutationFn: () => setChannelStatus(channel.slug, !channel.is_active),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [CHANNELS_KEY] });
    },
  });

  return (
    <TableRow>
      <TableCell className="font-medium">{channel.slug}</TableCell>
      <TableCell>{channel.name}</TableCell>
      <TableCell>{channel.currency}</TableCell>
      <TableCell>
        <Badge variant={channel.is_active ? "active" : "inactive"}>
          {channel.is_active ? t("active") : t("inactive")}
        </Badge>
      </TableCell>
      <TableCell>
        <Button
          size="sm"
          variant="outline"
          onClick={() => mutation.mutate()}
          disabled={mutation.isPending}
        >
          {channel.is_active ? t("deactivate") : t("activate")}
        </Button>
      </TableCell>
    </TableRow>
  );
}

export function ChannelsManager() {
  const t = useTranslations("channels");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [activeOnly, setActiveOnly] = useState(false);

  const query = useQuery({
    queryKey: [CHANNELS_KEY, { activeOnly }],
    queryFn: () => listChannels(activeOnly),
  });

  function refreshList() {
    void queryClient.invalidateQueries({ queryKey: [CHANNELS_KEY] });
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-xl font-semibold">{t("title")}</h1>

      <CreateChannelForm onCreated={refreshList} />

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={activeOnly}
          onChange={(e) => setActiveOnly(e.target.checked)}
        />
        {t("onlyActive")}
      </label>

      {query.isLoading ? <p>{tCommon("loading")}</p> : null}

      {query.isError ? (
        <Alert variant="destructive">
          {query.error instanceof ApiError
            ? query.error.detail
            : tCommon("genericError")}
        </Alert>
      ) : null}

      {query.data && query.data.length === 0 ? (
        <p className="text-muted-foreground">{t("noChannels")}</p>
      ) : null}

      {query.data && query.data.length > 0 ? (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("slug")}</TableHead>
              <TableHead>{t("name")}</TableHead>
              <TableHead>{t("currency")}</TableHead>
              <TableHead>{t("status")}</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {query.data.map((channel) => (
              <ChannelRow key={channel.slug} channel={channel} />
            ))}
          </TableBody>
        </Table>
      ) : null}
    </div>
  );
}
