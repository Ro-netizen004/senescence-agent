# Prospective reference specification only: NOT executed in E1-S V1.
# Future authorized invocation: Rscript independent_deseq2.R E1_ROOT NEW_E1S_DIR
args <- commandArgs(trailingOnly=TRUE)
stopifnot(length(args)==2L)
source_root <- normalizePath(args[1],mustWork=TRUE)
destination <- normalizePath(args[2],mustWork=FALSE)
if (dir.exists(destination) || startsWith(destination,paste0(source_root,"/"))) stop("New separate output directory required")
if (!requireNamespace("DESeq2",quietly=TRUE)) stop("DESeq2 unavailable")
if (as.character(packageVersion("DESeq2"))!="1.52.0") stop("Prospectively specified DESeq2 version differs")
dir.create(destination,recursive=TRUE)
writeLines(capture.output(sessionInfo()),file.path(destination,"SESSION_INFO.txt"))
targets <- c("ATP2A2","CYB5R4","ELOB","GATA3","KDM1A","MED24","MEN1","NFKB2","SGF29")
for (target in targets) {
  out <- file.path(destination,target);dir.create(out)
  writeLines("E1-S independent R fit; not original E1",file.path(out,"ATTEMPT.txt"))
  warnings <- character()
  success <- FALSE
  tryCatch(withCallingHandlers({
    counts <- as.matrix(read.csv(gzfile(file.path(source_root,"prepared",target,"counts.csv.gz")),row.names=1,check.names=FALSE))
    metadata <- read.csv(file.path(source_root,"prepared",target,"metadata.csv"),row.names=1,check.names=FALSE)
    stopifnot(identical(rownames(counts),rownames(metadata)),all(is.finite(counts)),all(counts>=0),all(counts==round(counts)),max(counts)<.Machine$integer.max)
    counts <- counts[,colSums(counts)>=10,drop=FALSE]
    metadata$donor_id <- factor(metadata$donor_id)
    metadata$perturbation <- factor(metadata$perturbation,levels=c("NTC","targeting"))
    dds <- DESeq2::DESeqDataSetFromMatrix(t(counts),metadata,~donor_id+perturbation)
    dds <- DESeq2::DESeq(dds,fitType="parametric",sfType="ratio",betaPrior=FALSE,minReplicatesForReplace=7,parallel=FALSE)
    result <- DESeq2::results(dds,contrast=c("perturbation","targeting","NTC"),alpha=.05,independentFiltering=TRUE)
    saveRDS(dds,file.path(out,"full_fit.rds"))
    write.csv(as.data.frame(result),file.path(out,"results.csv"))
    write.csv(as.data.frame(S4Vectors::mcols(dds)),file.path(out,"gene_diagnostics.csv"))
    write.csv(data.frame(sample=colnames(dds),size_factor=DESeq2::sizeFactors(dds)),file.path(out,"size_factors.csv"),row.names=FALSE)
    write.csv(model.matrix(~donor_id+perturbation,metadata),file.path(out,"design_matrix.csv"))
    writeLines(as.character(attr(DESeq2::dispersionFunction(dds),"fitType")),file.path(out,"actual_fit_type.txt"))
    success <- TRUE
  },warning=function(w){warnings <<- c(warnings,conditionMessage(w));invokeRestart("muffleWarning")}),
    error=function(e)writeLines(conditionMessage(e),file.path(out,"ERROR.txt")))
  writeLines(warnings,file.path(out,"WARNINGS.txt"))
  writeLines(if(success) "COMPLETE" else "FAILED_NO_RETRY",file.path(out,"STATUS.txt"))
  if(!success) break
}
