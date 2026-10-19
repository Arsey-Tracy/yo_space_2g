# YoSpaces

YoSpaces is a Django REST API and Next.js application for managing organizations,
community spaces, and communications.

## Spaces and members

Organization owners manage Spaces from the dashboard at `/app/spaces`. A Space
can be created, renamed, updated, or deleted; deleting a Space also removes its
members. Owners can add and remove members, import members from CSV, and export
the current member list.

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET`, `POST` | `/api/spaces/` | List owned Spaces or create a Space |
| `GET`, `PUT`, `PATCH`, `DELETE` | `/api/spaces/{space_id}/` | Read, update, or delete a Space |
| `GET`, `POST` | `/api/spaces/{space_id}/members/` | List or add members |
| `GET`, `PUT`, `DELETE` | `/api/spaces/{space_id}/members/{member_id}/` | Read, update, or remove a member |
| `POST` | `/api/spaces/{space_id}/members/import-csv/` | Import `name`, `phone_number`, and optional `role` columns |
| `GET` | `/api/spaces/{space_id}/members/export/` | Download the member list as CSV |

When a user belongs to multiple organizations, requests use the selected
`X-Organization-ID` sent by the authenticated frontend. Space list, create,
update, and delete operations are scoped to that organization and require its
owner.

## SMS broadcasts

Organization owners can send a message to all phone numbers currently attached
to one of their Spaces, either immediately or at a future time. SMS delivery
uses Africa's Talking and reserves one wallet credit per recipient. A provider
failure refunds the reserved credits.

### API

All endpoints require the authenticated user's bearer token (the Next.js app
also exposes them through its same-origin `/api/backend/` proxy).

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/api/sms/broadcasts/` | List broadcasts owned by the signed-in user |
| `POST` | `/api/sms/broadcasts/` | Create a draft, send immediately, or schedule a broadcast |
| `GET` | `/api/spaces/` | List Spaces available to the signed-in user |

Create a draft:

```json
{
  "space": 12,
  "message": "The community meeting starts at 6 PM.",
  "status": "draft"
}
```

Send immediately by setting `status` to `"sent"`. Schedule delivery by setting
`status` to `"scheduled"` and providing `scheduled_at` as a future ISO 8601
datetime, including a timezone offset. Scheduled messages use the Space's
membership at delivery time; the recipient and credit counts are finalized
when delivery succeeds. The API does not allow clients to set worker-managed
statuses such as `"sending"` or to change a broadcast's status after creation.

Responses include the broadcast `id`, `space_name`, `status`, `scheduled_at`,
`sent_at`, `recipients_count`, `cost_credits`, and `failure_reason`.

### Scheduled delivery

The Django project intentionally has no queue or Redis dependency. Configure
the deployment's cron service to run this command once per minute:

```powershell
python manage.py process_scheduled_broadcasts --limit 100
```

Use the project's configured Python executable in production. The command
claims due broadcasts before contacting the provider, processes up to the
requested limit, and marks unsuccessful broadcasts as failed. Ensure only the
cron runner has access to invoke this command.

### Provider configuration

Configure the Africa's Talking username and API key using environment
variables. Set `AFRICASTALKING_USE_SANDBOX=true` with the sandbox username/key
for non-production testing. Do not put provider credentials in source control.

## Language support

The application currently presents English only. Other language selections
were removed until translated product content is available; existing account
and organization language values are normalized to English by migration.

## Development and tests

Run the authentication, Spaces, and SMS tests with:

```powershell
python manage.py test account.tests spaces.tests sms.tests
```

Run frontend checks from `yo_space_nextjs_frontend/yospaces`:

```powershell
npm run lint
npm run build
```