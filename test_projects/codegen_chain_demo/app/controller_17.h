#pragma once
#include "service_17.h"
#include "model_17.h"
#include <memory>

class Controller17 {
public:
    Controller17();
    void initialize();
    void run();
private:
    std::unique_ptr<Service17> service_;
    std::shared_ptr<Model17> model_;
};
