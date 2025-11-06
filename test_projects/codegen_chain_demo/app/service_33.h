#pragma once
#include <functional>
#include <vector>

class Service33 {
public:
    Service33();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
