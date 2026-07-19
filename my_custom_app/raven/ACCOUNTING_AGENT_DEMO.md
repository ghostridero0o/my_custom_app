# Raven accounting agent demo

The demo watches receipt images in one Raven group, sends the image and nearby
text to the Raven OpenAI client, and creates a draft Payment Entry, Journal
Entry, or Petty Expense. It never submits accounting documents.

Configure the integration from the **Raven Accounting Settings** Single
DocType. It contains the Raven channel and bot, AI model and confidence,
company defaults, petty expense accounts, and journal entry accounts. No
`raven_accounting_*` keys are required in `site_config.json`.

Raven Settings must have AI Integration enabled and a valid OpenAI API key.
The configured bot is used only as the sender of result messages. If the
configured channel is omitted, a non-DM channel named `thu-chi`,
`thu chi`, or `thu–chi` is used.

After installing or updating the DocType:

```shell
bench --site SITE_NAME migrate
bench --site SITE_NAME clear-cache
bench restart
```

Test by posting an image with a caption such as:

```text
Chi tiền mặt mua văn phòng phẩm cho dự án ABC, tạo chứng từ nháp giúp mình.
```

The worker should post either a link to a draft document or a clarification
message in the same channel. Errors are recorded under the title
`Raven Accounting Agent` in Frappe Error Log.
