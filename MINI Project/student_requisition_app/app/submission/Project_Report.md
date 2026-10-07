# Student Academic Requisition Portal

**Short Project Report**

**Student / Group:** ____________________  **Class:** ____________________  **Date:** ____________________

## Objective

The project provides students with an online way to complete the institute's Student Academic Requisition Form, review the completed form, submit a request, and download a matching PDF. It also gives students a way to track requests and provides institute staff with request-management tools.

## Technology

The application is written in Python using Streamlit. It stores requisitions and status history in SQLite, validates form data with project-specific Python logic, and generates A4 PDFs with ReportLab. Pillow and pypdfium2 support signature images and in-app PDF previews.

## Main Features

- Student form for personal details, request type, purpose, supporting documents, and declaration.
- Validation of required fields, email, Indian mobile number, dates, uploads, and form text limits.
- PDF preview before confirmation; a requisition number is assigned after submission.
- PDF download, status tracking, request history, and withdrawal while a request is still submitted.
- Staff sign-in, request search and filters, status updates with an audit trail, SLA indicators, and CSV export.
- Optional email notifications and a QR code on generated PDFs.

## Workflow and Storage

Students enter and validate their details, review a watermarked preview, then confirm submission. The application saves the request and its generated PDF in a SQLite-backed workflow. Status changes are retained in the history. The PDF follows the institute form layout and leaves HoD and Principal office fields blank for official processing.

## Security and Limitations

The application uses parameterized SQL, sanitizes uploaded filenames, checks upload content, and supports configured staff credentials. Students are not authenticated, and staff permissions are not separated by department. Local SQLite and upload storage require a persistent disk in production; free ephemeral hosting can lose stored data after a restart. Configure non-demo staff credentials before deployment.

## Verification and Deployment

The repository includes automated tests and screenshots of the application workflow. The test suite was not run for this package because `pytest` is not installed in the project's current virtual environment. A public deployment URL has not yet been configured; see `Deployment_Link.txt` for the remaining deployment step.