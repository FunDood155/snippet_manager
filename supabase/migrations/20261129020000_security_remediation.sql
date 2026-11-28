BEGIN;

CREATE TABLE snippet_private.auth_transitions (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    pending text CHECK (pending IN ('oauth', 'recovery')),
    operation_id uuid,
    oauth_invalid_through timestamptz,
    CHECK ((pending IS NULL) = (operation_id IS NULL))
);
REVOKE ALL ON snippet_private.auth_transitions FROM PUBLIC, anon, authenticated, service_role;
GRANT SELECT, INSERT, UPDATE ON snippet_private.auth_transitions TO snippet_app;

-- Return only a yes/no match. Runtime has no direct access to Auth tables.
CREATE FUNCTION snippet_private.oauth_session_after(session_id uuid, owner_id uuid, client_id uuid, cutoff timestamptz)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = ''
AS $$
    SELECT EXISTS (
        SELECT 1 FROM auth.sessions s
        WHERE s.id = session_id AND s.user_id = owner_id AND s.oauth_client_id = client_id
          AND s.created_at > cutoff
    );
$$;
REVOKE ALL ON FUNCTION snippet_private.oauth_session_after(uuid, uuid, uuid, timestamptz)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION snippet_private.oauth_session_after(uuid, uuid, uuid, timestamptz) TO snippet_app;

-- Provider grant revocation covers sessions, but an approved authorization
-- can outlive it. Bound admission by the expiry of still-outstanding codes.
CREATE FUNCTION snippet_private.oauth_revocation_boundary(owner_id uuid, target_client uuid)
RETURNS timestamptz LANGUAGE sql VOLATILE SECURITY DEFINER SET search_path = ''
AS $$
    SELECT greatest(clock_timestamp(), max(a.expires_at))
    FROM auth.oauth_authorizations a
    WHERE a.user_id = owner_id AND a.client_id = target_client
      AND a.authorization_code IS NOT NULL AND a.expires_at > statement_timestamp();
$$;
REVOKE ALL ON FUNCTION snippet_private.oauth_revocation_boundary(uuid, uuid)
    FROM PUBLIC, anon, authenticated, service_role;
GRANT EXECUTE ON FUNCTION snippet_private.oauth_revocation_boundary(uuid, uuid) TO snippet_app;

CREATE INDEX email_flows_owner_idx ON snippet_private.email_flows (owner_id);
CREATE INDEX auth_limits_window_idx ON snippet_private.auth_limits (window_id, bucket);
CREATE INDEX snippets_owner_id_sno_idx ON public.snippets (owner_id, sno);

COMMIT;
