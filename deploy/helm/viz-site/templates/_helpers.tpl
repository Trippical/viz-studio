{{- define "viz-site.name" -}}
{{- .Chart.Name -}}
{{- end -}}

{{/*
Standard fullname: the release name alone when it already contains the chart
name ("helm install viz-site ..." gives "viz-site", not "viz-site-viz-site"),
otherwise "<release>-viz-site". Kubernetes names are capped at 63 characters.
*/}}
{{- define "viz-site.fullname" -}}
{{- if contains .Chart.Name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name .Chart.Name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{/*
ServiceAccount name: serviceAccount.name when set, otherwise the fullname.
The IRSA trust policy must name exactly this service account.
*/}}
{{- define "viz-site.serviceAccountName" -}}
{{- default (include "viz-site.fullname" .) .Values.serviceAccount.name -}}
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
