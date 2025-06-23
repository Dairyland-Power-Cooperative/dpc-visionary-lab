"use client";

import { useState, useEffect, Suspense } from "react";
import { PageHeader } from "@/components/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Input } from "@/components/ui/input";
import { getApiStatus } from "@/utils/env-utils";
import { Loader2, Check, AlertCircle, Plus, X, Shield } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { useImageSettings, BrandsProtectionMode } from "@/context/image-settings-context";
import { useSearchParams } from "next/navigation";
import { FadeScaleTransition } from "@/components/ui/page-transition";

// No longer need video settings types

// No longer need EnvVariables interface

interface ApiStatus {
  set: string[];
  missing: string[];
}

// Component that uses useSearchParams
function TabManager({ onTabChange }: { onTabChange: (tab: string) => void }) {
  const searchParams = useSearchParams();
  const tabParam = searchParams.get('tab');
  
  useEffect(() => {
    if (tabParam) {
      onTabChange(tabParam);
    }
  }, [tabParam, onTabChange]);
  
  return null;
}

export default function SettingsPage() {
  // Get image settings from context
  const imageSettings = useImageSettings();
  
  // State for handling new brand input
  const [newBrand, setNewBrand] = useState("");
  
  // Active tab state with default value
  const [activeTab, setActiveTab] = useState("brand");

  const [apiStatus, setApiStatus] = useState<ApiStatus | null>(null);
  const [apiStatusLoading, setApiStatusLoading] = useState(true);

  useEffect(() => {
    const fetchApiStatus = async () => {
      try {
        const data = await getApiStatus();
        setApiStatus(data);
      } catch (error) {
        console.error("Failed to fetch API status:", error);
      } finally {
        setApiStatusLoading(false);
      }
    };

    fetchApiStatus();
  }, []);

  // No longer need video settings functions

  const handleAddBrand = () => {
    if (newBrand.trim() && imageSettings.settings.brandsList.length < 3) {
      imageSettings.addBrand(newBrand);
      setNewBrand("");
    }
  };

  return (
    <FadeScaleTransition>
      <PageHeader title="Settings" />
      
      {/* Wrap the useSearchParams hook in a Suspense boundary */}
      <Suspense fallback={null}>
        <TabManager onTabChange={setActiveTab} />
      </Suspense>
      
      <div className="flex flex-col h-full p-8">
        <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
          <TabsList className="mb-6">
            <TabsTrigger value="brand">Brand Protection</TabsTrigger>
            <TabsTrigger value="api">API Status</TabsTrigger>
          </TabsList>

          <TabsContent value="brand" className="space-y-6">
            <Card>
              <CardHeader>
                <CardTitle>Brand Protection</CardTitle>
                <CardDescription>Configure brand protection settings for both image and video generation</CardDescription>
              </CardHeader>
              <CardContent className="space-y-6">
                <div className="space-y-4">
                  <h3 className="text-lg font-medium">Protection Settings</h3>
                  <p className="text-sm text-muted-foreground">
                    Configure how protected brands are handled during content generation
                  </p>
                  
                  <div className="space-y-2">
                    <Label htmlFor="brandProtection">Protection Mode</Label>
                    <Select 
                      value={imageSettings.settings.brandsProtection} 
                      onValueChange={(value) => 
                        imageSettings.updateSettings({ brandsProtection: value as BrandsProtectionMode })
                      }
                    >
                      <SelectTrigger id="brandProtection" className="w-full">
                        <SelectValue placeholder="Select brand protection mode" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="off">Off</SelectItem>
                        <SelectItem value="neutralize">Neutralize</SelectItem>
                        <SelectItem value="replace">Replace</SelectItem>
                      </SelectContent>
                    </Select>
                    <p className="text-xs text-muted-foreground mt-1">
                      {imageSettings.settings.brandsProtection === 'neutralize' && 
                        "Neutralize: Replaces competitor brands with generic terms"}
                      {imageSettings.settings.brandsProtection === 'replace' && 
                        "Replace: Substitutes competitor brands with your protected brands"}
                      {imageSettings.settings.brandsProtection === 'off' && 
                        "Off: No brand protection applied"}
                    </p>
                  </div>
                  
                  {imageSettings.settings.brandsProtection !== 'off' && (
                    <div className="space-y-3 mt-4">
                      <Label>Protected Brands</Label>
                      <p className="text-xs text-muted-foreground">
                        Add up to 3 brands to protect in generated content
                      </p>
                      
                      <div className="space-y-2 mt-2">
                        {imageSettings.settings.brandsList.length > 0 ? (
                          <div className="flex flex-col gap-2">
                            {imageSettings.settings.brandsList.map(brand => (
                              <div key={brand} className="flex items-center justify-between p-2 bg-muted/40 rounded-md">
                                <div className="flex items-center">
                                  <Shield className="h-4 w-4 mr-2 text-primary" />
                                  <span>{brand}</span>
                                </div>
                                <Button
                                  size="icon"
                                  variant="ghost"
                                  className="h-8 w-8"
                                  onClick={() => imageSettings.removeBrand(brand)}
                                >
                                  <X className="h-4 w-4" />
                                </Button>
                              </div>
                            ))}
                          </div>
                        ) : (
                          <div className="p-2 bg-muted/40 rounded-md text-sm text-muted-foreground">
                            No brands protected yet
                          </div>
                        )}
                      </div>
                      
                      {imageSettings.settings.brandsList.length < 3 && (
                        <div className="flex gap-2 mt-2">
                          <Input
                            value={newBrand}
                            onChange={(e) => setNewBrand(e.target.value)}
                            placeholder="Enter brand name"
                            className="flex-1"
                            onKeyDown={(e) => {
                              if (e.key === 'Enter') {
                                e.preventDefault();
                                handleAddBrand();
                              }
                            }}
                          />
                          <Button onClick={handleAddBrand} disabled={!newBrand.trim()}>
                            <Plus className="h-4 w-4 mr-1" />
                            Add
                          </Button>
                        </div>
                      )}
                      
                      {imageSettings.settings.brandsList.length > 0 && (
                        <div className="mt-4">
                          <Button 
                            variant="outline" 
                            size="sm"
                            onClick={imageSettings.clearBrands}
                          >
                            Clear All Brands
                          </Button>
                        </div>
                      )}
                    </div>
                  )}
                  

                </div>
              </CardContent>
            </Card>
          </TabsContent>
          
          <TabsContent value="api">
            <Card>
              <CardHeader>
                <CardTitle>API Status</CardTitle>
                <CardDescription>Status of API configuration for content generation capabilities</CardDescription>
              </CardHeader>
              <CardContent>
                {apiStatusLoading ? (
                  <div className="flex items-center justify-center py-8">
                    <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
                  </div>
                ) : apiStatus ? (
                  <div className="space-y-6">
                    <div className="p-4 bg-muted rounded-lg">
                      <p className="text-sm mb-2">This page shows the API keys and configuration settings available to the backend. A missing API key means the corresponding feature may not work properly.</p>
                    </div>

                    {/* Essential Keys Section */}
                    <Card>
                      <CardHeader className="pb-2">
                        <CardTitle className="text-md font-medium flex items-center">
                          <Check className="h-5 w-5 text-green-500 mr-2" />
                          Available Features
                        </CardTitle>
                        <CardDescription>
                          API keys that are configured and ready to use
                        </CardDescription>
                      </CardHeader>
                      <CardContent>
                        <div className="space-y-4">
                          {apiStatus.set.length > 0 ? (
                            <>
                                                             {/* Image Generation */}
                               <div className="border rounded-md p-3">
                                 <h3 className="text-sm font-medium mb-2">Image Generation</h3>
                                 <div className="flex flex-wrap gap-2">
                                   {apiStatus.set
                                     .filter(key => key.includes('OPENAI') || key.includes('DALLE') || key.includes('SD') || key.includes('IMAGEGEN'))
                                     .map((variable) => (
                                       <Badge key={variable} className="bg-green-100 text-green-800 hover:bg-green-200 flex items-center">
                                         <Check className="h-3 w-3 mr-1" />
                                         {variable}
                                       </Badge>
                                     ))}
                                   {apiStatus.set.filter(key => key.includes('OPENAI') || key.includes('DALLE') || key.includes('SD') || key.includes('IMAGEGEN')).length === 0 && (
                                     <p className="text-xs text-muted-foreground">No image generation APIs are configured</p>
                                   )}
                                 </div>
                               </div>

                              {/* Video Generation */}
                              <div className="border rounded-md p-3">
                                <h3 className="text-sm font-medium mb-2">Video Generation</h3>
                                <div className="flex flex-wrap gap-2">
                                  {apiStatus.set
                                    .filter(key => key.includes('SORA') || key.includes('REPLICATE') || key.includes('RUNWAY'))
                                    .map((variable) => (
                                      <Badge key={variable} className="bg-green-100 text-green-800 hover:bg-green-200 flex items-center">
                                        <Check className="h-3 w-3 mr-1" />
                                        {variable}
                                      </Badge>
                                    ))}
                                  {apiStatus.set.filter(key => key.includes('SORA') || key.includes('REPLICATE') || key.includes('RUNWAY')).length === 0 && (
                                    <p className="text-xs text-muted-foreground">No video generation APIs are configured</p>
                                  )}
                                </div>
                              </div>

                              {/* Language Models */}
                              <div className="border rounded-md p-3">
                                <h3 className="text-sm font-medium mb-2">Language Models & Analysis</h3>
                                <div className="flex flex-wrap gap-2">
                                  {apiStatus.set
                                    .filter(key => key.includes('GPT') || key.includes('LLM') || key.includes('ANTHROPIC') || key.includes('CLAUDE'))
                                    .map((variable) => (
                                      <Badge key={variable} className="bg-green-100 text-green-800 hover:bg-green-200 flex items-center">
                                        <Check className="h-3 w-3 mr-1" />
                                        {variable}
                                      </Badge>
                                    ))}
                                  {apiStatus.set.filter(key => key.includes('GPT') || key.includes('LLM') || key.includes('ANTHROPIC') || key.includes('CLAUDE')).length === 0 && (
                                    <p className="text-xs text-muted-foreground">No language models are configured</p>
                                  )}
                                </div>
                              </div>

                              
                            </>
                          ) : (
                            <div className="p-4 text-center text-muted-foreground bg-muted/20 rounded-md">
                              <p>No API keys are configured yet.</p>
                            </div>
                          )}
                        </div>
                      </CardContent>
                    </Card>
                    
                    {/* Missing Keys Section */}
                    {apiStatus.missing.length > 0 && (
                      <Card>
                        <CardHeader>
                          <CardTitle className="text-md font-medium flex items-center">
                            <AlertCircle className="h-5 w-5 text-amber-500 mr-2" />
                            Missing API Keys
                          </CardTitle>
                          <CardDescription>
                            These keys would enable additional features
                          </CardDescription>
                        </CardHeader>
                        <CardContent>
                          <div className="space-y-4">
                            {/* Essential Missing Keys */}
                            <div className="border border-amber-200 rounded-md p-3 bg-amber-50/50">
                              <h3 className="text-sm font-medium mb-2 text-amber-700">Recommended Keys</h3>
                              <div className="flex flex-wrap gap-2">
                                                                 {apiStatus.missing
                                   .filter(key => 
                                     key.includes('OPENAI') || 
                                     key.includes('DALLE') || 
                                     key.includes('IMAGEGEN')
                                   )
                                   .map((variable) => (
                                      <Badge key={variable} variant="outline" className="bg-amber-50 text-amber-800 border-amber-200 hover:bg-amber-100">
                                        {variable}
                                      </Badge>
                                    ))}
                                 {apiStatus.missing.filter(key => 
                                   key.includes('OPENAI') || 
                                   key.includes('DALLE') || 
                                   key.includes('IMAGEGEN')
                                 ).length === 0 && (
                                   <p className="text-xs text-muted-foreground">All recommended keys are configured!</p>
                                 )}
                              </div>
                                                             <p className="text-xs text-amber-700 mt-2">
                                 These keys are needed for basic image generation functionality.
                               </p>
                            </div>
                            
                            {/* Optional Missing Keys */}
                            <div className="border rounded-md p-3">
                              <h3 className="text-sm font-medium mb-2">Optional Keys</h3>
                              <div className="flex flex-wrap gap-2">
                                                                 {apiStatus.missing
                                   .filter(key => 
                                     !key.includes('OPENAI') && 
                                     !key.includes('DALLE') && 
                                     !key.includes('IMAGEGEN')
                                   )
                                  .map((variable) => (
                                    <Badge key={variable} variant="outline" className="border-muted-foreground/20 hover:bg-muted/50">
                                      {variable}
                                    </Badge>
                                  ))}
                              </div>
                              <p className="text-xs text-muted-foreground mt-2">
                                These keys enable additional features but aren&apos;t required for basic functionality.
                              </p>
                            </div>
                            
                            <div className="mt-4 p-3 bg-blue-50 rounded-md">
                              <div className="flex items-start">
                                <AlertCircle className="h-4 w-4 text-blue-500 mt-0.5 mr-2" />
                                <div>
                                  <p className="text-xs text-blue-700">
                                    Configure your API keys by adding them to your .env file or through your deployment platform&apos;s environment variables.
                                  </p>
                                </div>
                              </div>
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                ) : (
                  <div className="py-8 text-center text-muted-foreground">
                    <AlertCircle className="h-8 w-8 mx-auto mb-4 text-red-500" />
                    <p>Failed to connect to the API.</p>
                    <p className="text-sm mt-1">
                      Check if the API server is running at {process.env.NEXT_PUBLIC_API_PROTOCOL || 'http'}://{process.env.NEXT_PUBLIC_API_HOSTNAME || '127.0.0.1'}:{process.env.NEXT_PUBLIC_API_PORT || '8000'}
                    </p>
                  </div>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </FadeScaleTransition>
  );
}