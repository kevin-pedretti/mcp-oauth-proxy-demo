{{- define "mcp-oauth2-demo.name" -}}
{{- .Chart.Name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "mcp-oauth2-demo.fullname" -}}
{{- if .Release.Name | eq .Chart.Name }}
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

{{/* Name of the Secret containing JWT_SECRET */}}
{{- define "mcp-oauth2-demo.secretName" -}}
{{- if .Values.auth.existingSecret }}
{{- .Values.auth.existingSecret }}
{{- else }}
{{- include "mcp-oauth2-demo.fullname" . }}
{{- end }}
{{- end }}
