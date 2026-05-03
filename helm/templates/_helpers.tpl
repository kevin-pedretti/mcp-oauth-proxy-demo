{{- define "mcp-oauth2-demo.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mcp-oauth2-demo.fullname" -}}
{{- if eq .Release.Name .Chart.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}

{{- define "mcp-oauth2-demo.labels" -}}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{ include "mcp-oauth2-demo.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{- define "mcp-oauth2-demo.selectorLabels" -}}
app.kubernetes.io/name: {{ include "mcp-oauth2-demo.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/* Name of the Secret containing OIDC_CLIENT_SECRET */}}
{{- define "mcp-oauth2-demo.secretName" -}}
{{- if .Values.auth.existingSecret }}
{{- .Values.auth.existingSecret }}
{{- else }}
{{- include "mcp-oauth2-demo.fullname" . }}
{{- end }}
{{- end }}

{{/* Name of the PVC backing per-user state */}}
{{- define "mcp-oauth2-demo.pvcName" -}}
{{- if .Values.persistence.existingClaim }}
{{- .Values.persistence.existingClaim }}
{{- else }}
{{- include "mcp-oauth2-demo.fullname" . }}
{{- end }}
{{- end }}

{{/*
Validate mutually-exclusive value combinations. Call this from a template
that always renders (e.g. deployment.yaml) so misconfigurations fail at
`helm install`/`upgrade` time rather than producing a silently-broken release.
*/}}
{{- define "mcp-oauth2-demo.validate" -}}
{{- if and .Values.auth.existingSecret .Values.auth.oidcClientSecret -}}
{{- fail "auth.existingSecret and auth.oidcClientSecret are mutually exclusive: when existingSecret is set, the chart will not render its own Secret and oidcClientSecret is silently ignored. Set only one." -}}
{{- end -}}
{{- if not .Values.auth.oidcConfigUrl -}}
{{- fail "auth.oidcConfigUrl is required: set it to your OIDC provider's openid-configuration URL (e.g. https://YOUR_TENANT.auth0.com/.well-known/openid-configuration)" -}}
{{- end -}}
{{- if not .Values.auth.oidcClientId -}}
{{- fail "auth.oidcClientId is required: set it to your OAuth application's client ID" -}}
{{- end -}}
{{- if and (not .Values.auth.oidcClientSecret) (not .Values.auth.existingSecret) -}}
{{- fail "auth.oidcClientSecret (or auth.existingSecret) is required: set the client secret literally, or point to a pre-existing Kubernetes Secret via auth.existingSecret" -}}
{{- end -}}
{{- end -}}
