{{- define "viz-site.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{- define "viz-site.fullname" -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "viz-site.labels" -}}
app.kubernetes.io/name: {{ include "viz-site.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}

{{- define "viz-site.selectorLabels" -}}
app.kubernetes.io/name: {{ include "viz-site.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "viz-site.probeHost" -}}
{{- index (splitList "," .Values.allowedHosts) 0 | trim -}}
{{- end -}}
