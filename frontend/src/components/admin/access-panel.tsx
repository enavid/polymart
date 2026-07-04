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
  assignRole,
  createUser,
  grantChannel,
  listUsers,
  type UserAccount,
} from "@/lib/api/access";
import { ApiError } from "@/lib/api/client";

type AdminT = ReturnType<typeof useTranslations<"admin">>;
type CommonT = ReturnType<typeof useTranslations<"common">>;

// The user picker fetches the whole roster; the roster is small in practice and
// paging a chooser adds friction, so one generous page is fetched up front.
const USERS_QUERY_KEY = ["access-users"] as const;
const USERS_PAGE_LIMIT = 100;

/** Map an access error to a localized message; 403 is the common gate failure. */
function errorMessage(
  error: unknown,
  isError: boolean,
  t: AdminT,
  tCommon: CommonT,
): string | null {
  if (error instanceof ApiError) {
    return error.status === 403 ? t("forbidden") : error.detail;
  }
  return isError ? tCommon("genericError") : null;
}

/** A human label for a user in the picker: name if known, else the phone. */
function userLabel(user: UserAccount): string {
  const base = user.full_name.trim() || user.phone_number;
  return `${base} (#${user.id})`;
}

/** A labelled dropdown of user accounts; the empty value means "none chosen". */
function UserSelect({
  id,
  users,
  value,
  onChange,
}: {
  id: string;
  users: UserAccount[];
  value: string;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("admin");
  return (
    <div className="flex flex-col gap-1.5">
      <Label htmlFor={id}>{t("selectUser")}</Label>
      <select
        id={id}
        name={id}
        className="h-10 rounded-md border border-input bg-background px-3 text-sm"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required
      >
        <option value="">{t("selectUserPlaceholder")}</option>
        {users.map((user) => (
          <option key={user.id} value={String(user.id)}>
            {userLabel(user)}
          </option>
        ))}
      </select>
    </div>
  );
}

function RoleAssignmentForm({ users }: { users: UserAccount[] }) {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const [userId, setUserId] = useState("");
  const [role, setRole] = useState("");

  const mutation = useMutation({
    mutationFn: () => assignRole(Number(userId), role),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("assignRoleTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <UserSelect id="role_user" users={users} value={userId} onChange={setUserId} />
          <FormField
            id="role_name"
            label={t("role")}
            value={role}
            onChange={(e) => setRole(e.target.value)}
            required
          />
          {mutation.isSuccess ? (
            <Alert variant="success">{t("assignRoleSuccess")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending || !userId}>
            {mutation.isPending ? tCommon("loading") : t("assignRoleCta")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function ChannelGrantForm({ users }: { users: UserAccount[] }) {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const [userId, setUserId] = useState("");
  const [channelSlug, setChannelSlug] = useState("");

  const mutation = useMutation({
    mutationFn: () => grantChannel(Number(userId), channelSlug),
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const error = errorMessage(mutation.error, mutation.isError, t, tCommon);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("grantChannelTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
          <UserSelect id="grant_user" users={users} value={userId} onChange={setUserId} />
          <FormField
            id="grant_channel_slug"
            label={t("channelSlug")}
            value={channelSlug}
            onChange={(e) => setChannelSlug(e.target.value)}
            required
          />
          {mutation.isSuccess ? (
            <Alert variant="success">{t("grantChannelSuccess")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending || !userId}>
            {mutation.isPending ? tCommon("loading") : t("grantChannelCta")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function CreateUserForm() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");
  const queryClient = useQueryClient();
  const [phoneNumber, setPhoneNumber] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [isStaff, setIsStaff] = useState(false);

  const mutation = useMutation({
    mutationFn: () =>
      createUser({
        phone_number: phoneNumber,
        password,
        full_name: fullName,
        is_staff: isStaff,
      }),
    onSuccess: () => {
      // Refresh the roster so the new account appears in the pickers immediately.
      queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY });
      setPhoneNumber("");
      setPassword("");
      setFullName("");
      setIsStaff(false);
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  // 409 -> already exists, 400 -> invalid phone; other statuses fall through.
  let error: string | null = null;
  if (mutation.error instanceof ApiError) {
    if (mutation.error.status === 403) error = t("forbidden");
    else if (mutation.error.status === 409) error = t("userExists");
    else if (mutation.error.status === 400) error = t("invalidPhone");
    else error = mutation.error.detail;
  } else if (mutation.isError) {
    error = tCommon("genericError");
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("createUserTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {/* method="post" plus a name-less password: a non-hydrated native submit
            stays a POST with the value in the body, never a GET that leaks it. */}
        <form onSubmit={onSubmit} method="post" className="flex flex-col gap-4" noValidate>
          <FormField
            id="new_user_phone"
            label={tCommon("phoneNumber")}
            type="tel"
            inputMode="tel"
            autoComplete="off"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            required
          />
          <FormField
            id="new_user_password"
            label={tCommon("password")}
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            omitName
          />
          <FormField
            id="new_user_full_name"
            label={t("fullName")}
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
          />
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isStaff}
              onChange={(e) => setIsStaff(e.target.checked)}
            />
            {t("isStaff")}
          </label>
          {mutation.isSuccess ? (
            <Alert variant="success">{t("createUserSuccess")}</Alert>
          ) : null}
          {error ? <Alert variant="destructive">{error}</Alert> : null}
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? tCommon("loading") : t("createUserCta")}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

function UsersList({ users }: { users: UserAccount[] }) {
  const t = useTranslations("admin");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("usersTitle")}</CardTitle>
      </CardHeader>
      <CardContent>
        {users.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("usersEmpty")}</p>
        ) : (
          <ul className="flex flex-col divide-y divide-border text-sm">
            {users.map((user) => (
              <li key={user.id} className="flex items-center justify-between gap-2 py-2">
                <span>
                  <span className="text-muted-foreground">#{user.id}</span>{" "}
                  {user.full_name.trim() || user.phone_number}
                </span>
                {user.is_staff ? (
                  <span className="rounded bg-muted px-2 py-0.5 text-xs text-muted-foreground">
                    {t("staffBadge")}
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function AccessPanel() {
  const t = useTranslations("admin");
  const tCommon = useTranslations("common");

  const usersQuery = useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: () => listUsers({ limit: USERS_PAGE_LIMIT }),
  });
  const users = usersQuery.data?.results ?? [];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-xl font-semibold">{t("accessTitle")}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t("userManagementNote")}</p>
      </div>

      {usersQuery.isLoading ? <Loading label={tCommon("loading")} /> : null}
      {usersQuery.isError ? (
        <Alert variant="destructive">{t("usersLoadError")}</Alert>
      ) : null}

      <div className="grid gap-6 md:grid-cols-2">
        <UsersList users={users} />
        <CreateUserForm />
        <RoleAssignmentForm users={users} />
        <ChannelGrantForm users={users} />
      </div>
    </div>
  );
}
