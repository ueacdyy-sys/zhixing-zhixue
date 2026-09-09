pluginManagement {
    repositories {
        // 国内镜像优先（阿里云），官方库兜底
        maven { url = uri("https://maven.aliyun.com/repository/gradle-plugin") }
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/central") }
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}
plugins {
    id("org.gradle.toolchains.foojay-resolver-convention") version "1.0.0"
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        // Verified artifacts downloaded through IDM are staged here first, so
        // offline builds never fall back to an uncontrolled network fetch.
        maven { url = uri("$rootDir/vendor-maven") }
        // 国内镜像优先（阿里云），官方库兜底
        maven { url = uri("https://maven.aliyun.com/repository/google") }
        maven { url = uri("https://maven.aliyun.com/repository/central") }
        google()
        mavenCentral()
    }
}

enableFeaturePreview("TYPESAFE_PROJECT_ACCESSORS")

rootProject.name = "ZhixingZhixueMobile"

include(":app")
include(":common")
include(":rtsp")
include(":learning-domain")
include(":learning-application")
include(":edge-android")
