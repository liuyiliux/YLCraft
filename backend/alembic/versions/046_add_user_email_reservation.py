"""reserve optional user email for future production registration flows"""

import sqlalchemy as sa
from alembic import op

revision = "046_add_user_email_reservation"
down_revision = "045_add_users_sessions_and_owners"
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("users", sa.Column("email", sa.String(length=320), nullable=True))
    op.create_index("ix_users_email", "users", ["email"], unique=True)

def downgrade() -> None:
    op.drop_index("ix_users_email", table_name="users")
    op.drop_column("users", "email")
